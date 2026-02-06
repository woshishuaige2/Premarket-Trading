"""
Premarket Shock & Confirm Momentum Strategy - Core Logic
Shared between realtime and backtest paths.
"""
import math
from datetime import datetime, time as dt_time
import strategy_config as config

class MarketData:
    """Container for symbol-specific market data and bar history."""
    def __init__(self, symbol, price=0.0):
        self.symbol = symbol
        self.price = price
        self.vwap = 0.0
        self.bid = 0.0
        self.ask = 0.0
        self.volume = 0
        self.bars_1s = [] # List of BarData-like dicts
        self.bars_5s = []
        self.med_vol_1s = 0.0
        self.med_vol_5s = 0.0
        self.med_range_5s = 0.0

class StrategyLogic:
    """Stateless logic for strategy triggers and exits."""
    
    @staticmethod
    def is_in_window(dt: datetime) -> bool:
        """Check if current time is within any premarket trading window."""
        current_time = dt.strftime("%H:%M:%S")
        for start, end in config.PREMARKET_WINDOWS:
            if start <= current_time <= end:
                return True
        return False

    @staticmethod
    def check_shock_1s(data: MarketData) -> (bool, str):
        """LAYER A: SHOCK DETECTOR (1s)."""
        if not data.bars_1s:
            return False, "No 1s data"
            
        last_1s = data.bars_1s[-1]
        
        # Avoid division by zero
        if last_1s['open'] == 0:
            return False, "Invalid bar: open=0"
            
        ret_1s = (last_1s['close'] - last_1s['open']) / last_1s['open']
        
        # Primary check: 1s shock
        is_shock = (ret_1s >= config.SHOCK_RET_1S and 
                    last_1s['volume'] >= config.SHOCK_VOL_MULT_1S * data.med_vol_1s)
        
        # Alternative: 2s shock
        if not is_shock and len(data.bars_1s) >= 2:
            prev_1s = data.bars_1s[-2]
            if prev_1s['open'] > 0:
                ret_2s = (last_1s['close'] - prev_1s['open']) / prev_1s['open']
                vol_2s = last_1s['volume'] + prev_1s['volume']
                is_shock = (ret_2s >= config.SHOCK_RET_2S and 
                            vol_2s >= config.SHOCK_VOL_MULT_2S * data.med_vol_1s)
        
        reason = f"Shock: {ret_1s:.2%} ret, {last_1s['volume']:.0f} vol (vs {data.med_vol_1s:.0f} med)"
        return is_shock, reason

    @staticmethod
    def check_confirm_5s(data: MarketData) -> (bool, str):
        """LAYER B: CONTINUATION CONFIRM (5s)."""
        if not data.bars_5s:
            return False, "No 5s data"
            
        last_5s = data.bars_5s[-1]
        
        # Avoid division by zero
        if last_5s['open'] == 0:
            return False, "Invalid bar: open=0"
        
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
        
        # Must hold within top X% of the 5s range
        pullback = last_5s.high - data.price
        return pullback <= (1.0 - config.NO_FADE_FRAC) * range_5s

    @staticmethod
    def check_exec_safety(data: MarketData) -> (bool, str):
        """Execution constraints using IBKR bid/ask."""
        if data.bid == 0 or data.ask == 0:
            return False, "No bid/ask"
            
        spread_pct = (data.ask - data.bid) / data.bid
        if spread_pct > config.MAX_SPREAD_PCT / 100.0:
            return False, f"Spread too wide: {spread_pct:.2%}"
            
        # Spread relative to move magnitude
        if data.bars_5s:
            last_5s = data.bars_5s[-1]
            if last_5s.open > 0:
                ret_5s_abs = abs((last_5s.close - last_5s.open) / last_5s.open)
                if ret_5s_abs > 0 and spread_pct > config.SPREAD_REL_MULT * ret_5s_abs:
                    return False, f"Spread too wide rel to move: {spread_pct:.2%} vs {ret_5s_abs:.2%}"
            
        return True, "EXEC_OK"

    @staticmethod
    def check_exit(data: MarketData, entry_price: float, entry_time: datetime, max_price: float) -> (bool, str):
        """Risk management exits."""
        if data.price <= 0: return False, ""
        
        # 1. Hard Stop
        if data.price <= entry_price * (1.0 - config.STOP_PCT):
            return True, "HARD_STOP"
            
        # 2. Weakness Exit (Fail-fast on 1s drop)
        if data.bars_1s:
            last_1s = data.bars_1s[-1]
            if last_1s['open'] > 0:
                ret_1s = (last_1s['close'] - last_1s['open']) / last_1s['open']
                if ret_1s <= -config.FAIL_RET_1S:
                    return True, "WEAKNESS_EXIT"
        
        # 3. Take Profit (R-multiple)
        risk = entry_price * config.STOP_PCT
        target = entry_price + (risk * config.TP_R_MULT)
        if data.price >= target:
            return True, "TAKE_PROFIT"
            
        # 4. Time Stop (Trailing-style)
        elapsed = (datetime.now() - entry_time).total_seconds()
        if elapsed >= config.TIME_STOP_SECONDS:
            pnl_r = (data.price - entry_price) / risk
            if pnl_r < config.MIN_PNL_AT_TIME:
                return True, "TIME_STOP"
                
        return False, ""

    @staticmethod
    def calculate_medians(bars, window_seconds=120):
        """Calculate rolling medians for volume and range."""
        if not bars: return 1.0, 0.01 # Robust floor
        
        # In a real implementation, we'd filter by timestamp
        # For simplicity, we'll take the last N bars
        volumes = sorted([b.volume if hasattr(b, 'volume') else b['volume'] for b in bars])
        
        if not volumes: return 1.0, 0.01
        
        mid = len(volumes) // 2
        med_vol = volumes[mid] if len(volumes) % 2 != 0 else (volumes[mid-1] + volumes[mid]) / 2.0
        
        ranges = []
        for b in bars:
            if hasattr(b, 'high'):
                ranges.append(b.high - b.low)
            else:
                ranges.append(b['high'] - b['low'])
        
        ranges.sort()
        if not ranges: return max(1.0, med_vol), 0.01
        
        mid_r = len(ranges) // 2
        med_range = ranges[mid_r] if len(ranges) % 2 != 0 else (ranges[mid_r-1] + ranges[mid_r]) / 2.0
        
        return max(1.0, med_vol), max(0.001, med_range)
