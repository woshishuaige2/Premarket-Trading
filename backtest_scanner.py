"""
Backtest Scanner for Premarket Strategy
Uses shared StrategyLogic to ensure consistency with live trading.
"""
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
from conditions import MarketData, Bar, StrategyLogic
import strategy_config as config

class BacktestEngine:
    def __init__(self, symbol: str, initial_capital: float = 10000.0):
        self.symbol = symbol
        self.capital = initial_capital
        self.market_data = MarketData(symbol=symbol, timestamp=datetime.now(), price=0.0)
        
        # History for backtest
        self.full_history: List[Bar] = []
        self.trades = []
        
        # State
        self.state = "IDLE"
        self.entry_price = 0.0
        self.stop_price = 0.0
        self.entry_time = None
        self.R = 0.0
        self.shares = 0
        self.arm_time = None

    def load_tws_data(self, tws_app, date_str: str) -> Tuple[List[Bar], List[Bar]]:
        """Fetch 1s and 5s bars from TWS for a specific date."""
        # TWS expects "YYYYMMDD HH:MM:SS"
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
        # Use 9:30 AM to align with the end of premarket
        end_dt = target_date.replace(hour=8, minute=30, second=0)
        
        # Use exact format from Scanner-Alert: "1 D" and "YYYYMMDD HH:MM:SS US/Eastern"
        print(f"[BACKTEST] Requesting 5s bars for {self.symbol} on {date_str}...")
        bars_5s_raw = tws_app.fetch_historical_bars(self.symbol, end_dt, duration="1 D", bar_size="5 secs")
        print(f"[DEBUG] {self.symbol} 5s bars received: {len(bars_5s_raw)}")
        
        print(f"[BACKTEST] Requesting 1s bars for {self.symbol} on {date_str} (Multi-chunk)...")
        # 1s bars are limited to 1800-3600 seconds per request.
        # We fetch three 30-minute chunks to cover the most active premarket (08:00 - 09:30)
        bars_1s_raw = []
        for i in range(3):
            chunk_end = end_dt - timedelta(seconds=i * 1800)
            print(f"  > Fetching 1s chunk {i+1}/3 ending at {chunk_end.strftime('%H:%M:%S')}...")
            try:
                chunk_data = tws_app.fetch_historical_bars(
                    self.symbol,
                    chunk_end,
                    duration="1800 S",
                    bar_size="1 secs",
                    what_to_show=config.BACKTEST_1S_WHAT_TO_SHOW
                )
                if chunk_data and len(chunk_data) > 0:
                    bars_1s_raw.extend(chunk_data)
                    print(f"     Got {len(chunk_data)} bars")
                else:
                    print(f"     No data returned (empty or None)")
            except Exception as e:
                print(f"     Error fetching chunk: {e}")
                continue
            # Small sleep to avoid pacing violations
            time.sleep(0.5)
        
        # Sort and remove duplicates if any
        bars_1s_raw.sort(key=lambda x: x['date'])
        unique_bars = []
        last_date = None
        for b in bars_1s_raw:
            if b['date'] != last_date:
                unique_bars.append(b)
                last_date = b['date']
        bars_1s_raw = unique_bars
        print(f"[DEBUG] {self.symbol} 1s bars received (total): {len(bars_1s_raw)}")
        
        def convert_bars(raw_list):
            converted = []
            for b in raw_list:
                # b['date'] format: '20260129  07:00:00'
                ts = datetime.strptime(b['date'], "%Y%m%d  %H:%M:%S")
                converted.append(Bar(ts, b['open'], b['high'], b['low'], b['close'], b['volume'], b['average']))
            return converted

        return convert_bars(bars_1s_raw), convert_bars(bars_5s_raw)

    def add_bar_1s(self, bar: Bar):
        self.market_data.timestamp = bar.timestamp
        self.market_data.price = bar.close
        self.market_data.bars_1s.append(bar)
        
        # Maintain 1s window for medians
        if len(self.market_data.bars_1s) > 300:
            self.market_data.bars_1s.pop(0)
            
        # Mock bid/ask for backtest (0.01 spread)
        self.market_data.bid = bar.close - 0.005
        self.market_data.ask = bar.close + 0.005
        self.market_data.bid_time = bar.timestamp
        self.market_data.ask_time = bar.timestamp
        
        # Update medians
        mv1, _, _ = StrategyLogic.calculate_medians(self.market_data.bars_1s, 120)
        self.market_data.med_vol_1s = mv1
        
        self._process_logic()

    def add_bar_5s(self, bar: Bar):
        self.market_data.bars_5s.append(bar)
        if len(self.market_data.bars_5s) > 120:
            self.market_data.bars_5s.pop(0)
            
        # Update medians
        mv5, mr5, _ = StrategyLogic.calculate_medians(self.market_data.bars_5s, 120)
        self.market_data.med_vol_5s = mv5
        self.market_data.med_range_5s = mr5

    def _process_logic(self):
        ts_str = self.market_data.timestamp.strftime("%H:%M:%S")
        if self.state == "IDLE":
            if StrategyLogic.is_in_window(self.market_data.timestamp):
                # Fallback: If no 1s bars, use the latest 5s bar for shock detection
                if not self.market_data.bars_1s and self.market_data.bars_5s:
                    last_5s = self.market_data.bars_5s[-1]
                    # Simulate a 1s bar from the 5s bar for the detector
                    mock_1s = Bar(last_5s.timestamp, last_5s.open, last_5s.high, last_5s.low, last_5s.close, last_5s.volume // 5)
                    self.market_data.bars_1s = [mock_1s]
                
                # Debug print for specified time window
                if config.DEBUG_TIME_WINDOW and ts_str.startswith(config.DEBUG_TIME_WINDOW):
                    if self.market_data.bars_1s:
                        last_1s = self.market_data.bars_1s[-1]
                        ret_1s = (last_1s.close - last_1s.open) / last_1s.open if last_1s.open != 0 else 0
                        print(f"[DEBUG-{config.DEBUG_TIME_WINDOW}] {ts_str} | 1s bar: O={last_1s.open:.4f} H={last_1s.high:.4f} L={last_1s.low:.4f} C={last_1s.close:.4f} V={last_1s.volume:.0f} | Ret={ret_1s:.2%} | Med_Vol={self.market_data.med_vol_1s:.0f} | Threshold={config.SHOCK_RET_1S:.2%}, {config.SHOCK_VOL_MULT_1S}x")
                
                shock_ok, reason = StrategyLogic.check_shock_1s(self.market_data)
                
                # Also print shock check result for specified time window
                if config.DEBUG_TIME_WINDOW and ts_str.startswith(config.DEBUG_TIME_WINDOW):
                    print(f"[DEBUG-{config.DEBUG_TIME_WINDOW}] {ts_str} | Shock Check: {shock_ok} | {reason}")
                
                if shock_ok:
                    print(f"[DEBUG] {ts_str} {self.symbol} IDLE -> ARMED. Reason: {reason}")
                    self.state = "ARMED"
                    self.arm_time = self.market_data.timestamp

        elif self.state == "ARMED":
            elapsed = (self.market_data.timestamp - self.arm_time).total_seconds()
            if elapsed > config.ARM_TIMEOUT_SECONDS:
                print(f"[DEBUG] {ts_str} {self.symbol} ARMED -> IDLE (Timeout {elapsed}s)")
                self.state = "IDLE"
                return

            confirm_ok, c_reason = StrategyLogic.check_confirm_5s(self.market_data)
            no_fade = StrategyLogic.check_no_fade(self.market_data)
            
            if confirm_ok and no_fade:
                print(f"[DEBUG] {ts_str} {self.symbol} ARMED -> ENTRY. Reason: {c_reason}")
                # Execute Entry
                self.entry_price = self.market_data.ask
                med_range = self.market_data.med_range_5s
                stop_dist = max(0.01, config.STOP_RANGE_MULT * med_range, self.entry_price * config.STOP_PCT)
                self.stop_price = self.entry_price - stop_dist
                self.R = self.entry_price - self.stop_price
                self.entry_time = self.market_data.timestamp
                self.shares = int(config.INVESTMENT_PER_TRADE / self.entry_price)
                
                if self.shares > 0:
                    self.state = "IN_TRADE"
                    # logging would go here

        elif self.state == "IN_TRADE":
            exit_triggered, reason = StrategyLogic.check_exit(
                self.market_data, self.entry_price, self.stop_price, self.entry_time, self.R
            )
            if exit_triggered:
                exit_price = self.market_data.bid
                gross_pnl = (exit_price - self.entry_price) * self.shares
                investment = self.entry_price * self.shares
                
                # Calculate commissions
                if self.entry_price >= 1.0:
                    entry_commission = max(config.COMMISSION_MIN, self.shares * config.COMMISSION_PER_SHARE)
                    exit_commission = max(config.COMMISSION_MIN, self.shares * config.COMMISSION_PER_SHARE)
                else:
                    entry_commission = investment * config.COMMISSION_PERCENT_LOW
                    exit_commission = (exit_price * self.shares) * config.COMMISSION_PERCENT_LOW
                
                total_commission = entry_commission + exit_commission
                net_pnl = gross_pnl - total_commission
                pnl_pct = (net_pnl / investment * 100) if investment > 0 else 0
                
                self.trades.append({
                    'symbol': self.symbol,
                    'entry_time': self.entry_time,
                    'exit_time': self.market_data.timestamp,
                    'entry_price': self.entry_price,
                    'exit_price': exit_price,
                    'shares': self.shares,
                    'investment': investment,
                    'gross_pnl': gross_pnl,
                    'commission': total_commission,
                    'pnl': net_pnl,
                    'pnl_pct': pnl_pct,
                    'reason': reason
                })
                self.capital += net_pnl
                self.state = "IDLE"

def run_backtest(symbol: str, bars_1s: List[Bar], bars_5s: List[Bar]):
    engine = BacktestEngine(symbol)
    
    # We need to feed 1s and 5s bars in chronological order
    # For simplicity in this backtest script, we align them by timestamp
    all_events = []
    for b in bars_1s: all_events.append((b.timestamp, '1s', b))
    for b in bars_5s: all_events.append((b.timestamp, '5s', b))
    all_events.sort(key=lambda x: x[0])
    
    for ts, type, bar in all_events:
        if type == '1s':
            engine.add_bar_1s(bar)
        else:
            engine.add_bar_5s(bar)
            
    return engine.trades, engine.capital
