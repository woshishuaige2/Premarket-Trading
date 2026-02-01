"""
Premarket Shock & Confirm Momentum Strategy - Core Logic
Shared condition evaluation for both realtime and backtesting.
"""
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import strategy_config as config

@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float = 0.0

@dataclass
class MarketData:
    symbol: str
    timestamp: datetime
    price: float
    bid: float = 0.0
    ask: float = 0.0
    bid_time: Optional[datetime] = None
    ask_time: Optional[datetime] = None
    volume: float = 0.0
    vwap: float = 0.0
    
    # History for indicators (rolling windows)
    bars_1s: List[Bar] = field(default_factory=list)
    bars_5s: List[Bar] = field(default_factory=list)
    
    # Medians (calculated externally or updated here)
    med_vol_1s: float = 0.0
    med_vol_5s: float = 0.0
    med_range_5s: float = 0.0

class StrategyLogic:
    """
    Centralized logic for the Premarket Shock & Confirm strategy.
    Designed to be used by both realtime_runner and backtester.
    """
    
    @staticmethod
    def is_in_window(dt: datetime) -> bool:
        """Check if current time is within specified premarket windows."""
        time_str = dt.strftime("%H:%M:%S")
        for start, end in config.PREMARKET_WINDOWS:
            if start <= time_str <= end:
                return True
        return False

    @staticmethod
    def check_exec_safety(data: MarketData) -> Tuple[bool, str]:
        """EXEC_OK safety gate checks."""
        if data.bid <= 0 or data.ask <= 0:
            return False, "Missing bid/ask"
            
        mid = (data.bid + data.ask) / 2
        spread = data.ask - data.bid
        spread_pct = spread / mid
        
        # 1) Absolute cap
        if spread_pct > config.MAX_SPREAD_PCT:
            return False, f"Spread too wide: {spread_pct:.2%}"
            
        # 2) Relative cap to the move
        if not data.bars_5s:
            return False, "No 5s bars for relative spread check"
            
        last_5s = data.bars_5s[-1]
        ret_5s_abs = abs((last_5s.close - last_5s.open) / last_5s.open)
        if spread_pct > config.SPREAD_REL_MULT * ret_5s_abs:
            return False, f"Spread relative cap failed: {spread_pct:.2%} > {config.SPREAD_REL_MULT} * {ret_5s_abs:.2%}"
            
        # 3) Quote freshness
        now = data.timestamp
        if data.bid_time and data.ask_time:
            bid_age = (now - data.bid_time).total_seconds() * 1000
            ask_age = (now - data.ask_time).total_seconds() * 1000
            if bid_age > config.QUOTE_STALE_MS or ask_age > config.QUOTE_STALE_MS:
                return False, f"Stale quotes: bid {bid_age:.0f}ms, ask {ask_age:.0f}ms"
        
        return True, "EXEC_OK"

    @staticmethod
    def check_shock_1s(data: MarketData) -> Tuple[bool, str]:
        """LAYER A: SHOCK DETECTOR (1 second)."""
        if not data.bars_1s:
            return False, "No 1s data"
            
        last_1s = data.bars_1s[-1]
        ret_1s = (last_1s.close - last_1s.open) / last_1s.open
        
        is_shock = (ret_1s >= config.SHOCK_RET_1S and 
                    last_1s.volume >= config.SHOCK_VOL_MULT_1S * data.med_vol_1s)
        
        reason = f"Shock: {ret_1s:.2%} ret, {last_1s.volume:.0f} vol (vs {data.med_vol_1s:.0f} med)"
        return is_shock, reason

    @staticmethod
    def check_confirm_5s(data: MarketData) -> Tuple[bool, str]:
        """LAYER B: CONTINUATION CONFIRM (5 seconds)."""
        if not data.bars_5s:
            return False, "No 5s data"
            
        last_5s = data.bars_5s[-1]
        ret_5s = (last_5s.close - last_5s.open) / last_5s.open
        range_5s = last_5s.high - last_5s.low
        
        is_confirm = (ret_5s >= config.CONFIRM_RET_5S and 
                      last_5s.volume >= config.CONFIRM_VOL_MULT_5S * data.med_vol_5s and
                      range_5s >= config.RANGE_MULT_5S * data.med_range_5s)
        
        reason = f"Confirm: {ret_5s:.2%} ret, {last_5s.volume:.0f} vol, {range_5s:.3f} range"
        return is_confirm, reason

    @staticmethod
    def check_no_fade(data: MarketData) -> bool:
        """NO-INSTANT-FADE FILTER."""
        if not data.bars_5s:
            return False
        last_5s = data.bars_5s[-1]
        range_5s = last_5s.high - last_5s.low
        if range_5s == 0: return True
        return data.price >= last_5s.high - config.NO_FADE_FRAC * range_5s

    @staticmethod
    def calculate_medians(bars: List[Bar], window_seconds: int = 120) -> Tuple[float, float, float]:
        """Calculate rolling medians for volume and range."""
        if not bars:
            return 1.0, 0.001, 0.0 # Return small non-zero defaults
            
        # Filter bars within the window
        now = bars[-1].timestamp
        cutoff = now - timedelta(seconds=window_seconds)
        window_bars = [b for b in bars if b.timestamp >= cutoff]
        
        if len(window_bars) < 5: # If not enough history, use all available bars
            window_bars = bars[-10:]
            
        vols = [b.volume for b in window_bars if b.volume > 0]
        ranges = [b.high - b.low for b in window_bars if (b.high - b.low) > 0]
        
        med_vol = float(np.median(vols)) if vols else 1.0
        med_range = float(np.median(ranges)) if ranges else 0.001
        
        return max(1.0, med_vol), max(0.001, med_range), 0.0

    @staticmethod
    def check_exit(data: MarketData, entry_price: float, stop_price: float, entry_time: datetime, R: float) -> Tuple[bool, str]:
        """Evaluate exit conditions continuously."""
        # 1) HARD STOP
        if data.price <= stop_price:
            return True, "STOP"
            
        # Optional: FAIL_ACCEL (sudden 1s drop)
        if data.bars_1s:
            last_1s = data.bars_1s[-1]
            ret_1s = (last_1s.close - last_1s.open) / last_1s.open
            if ret_1s <= -config.FAIL_RET_1S:
                return True, "FAIL_ACCEL"

        # 2) WEAKNESS EXIT
        if len(data.bars_5s) >= 2:
            curr_5s = data.bars_5s[-1]
            prev_5s = data.bars_5s[-2]
            if curr_5s.close < curr_5s.open and curr_5s.close < prev_5s.low:
                return True, "WEAKNESS"

        # 3) TAKE PROFIT
        if data.price >= entry_price + config.TP_R_MULT * R:
            return True, "TAKE_PROFIT"

        # 4) TIME STOP
        elapsed = (data.timestamp - entry_time).total_seconds()
        if elapsed >= config.TIME_STOP_SECONDS:
            unrealized_pnl_r = (data.price - entry_price) / R
            if unrealized_pnl_r < config.MIN_PNL_AT_TIME:
                return True, "TIME_STOP"

        return False, ""
