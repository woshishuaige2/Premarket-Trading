"""
Backtest Scanner for Premarket Strategy
Uses shared StrategyLogic to ensure consistency with live trading.
"""
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
        # End of premarket window (9:30 AM)
        end_dt = target_date.replace(hour=9, minute=30, second=0)
        
        # Duration for 5s bars: 14400 S = 4 hours
        print(f"[BACKTEST] Fetching 5s bars for {self.symbol} on {date_str}...")
        bars_5s_raw = tws_app.fetch_historical_bars(self.symbol, end_dt, duration="14400 S", bar_size="5 secs")
        
        # Duration for 1s bars: 7200 S = 2 hours
        # IBKR has strict limits on 1s duration requests (often max 1800s or 3600s).
        # We try 3600 S first for the most recent premarket hour.
        print(f"[BACKTEST] Fetching 1s bars for {self.symbol} on {date_str}...")
        bars_1s_raw = tws_app.fetch_historical_bars(self.symbol, end_dt, duration="3600 S", bar_size="1 secs")
        
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
        if self.state == "IDLE":
            if StrategyLogic.is_in_window(self.market_data.timestamp):
                shock_ok, _ = StrategyLogic.check_shock_1s(self.market_data)
                if shock_ok:
                    self.state = "ARMED"
                    self.arm_time = self.market_data.timestamp

        elif self.state == "ARMED":
            if (self.market_data.timestamp - self.arm_time).total_seconds() > config.ARM_TIMEOUT_SECONDS:
                self.state = "IDLE"
                return

            confirm_ok, _ = StrategyLogic.check_confirm_5s(self.market_data)
            # In backtest we assume safety_ok is true or mock it
            no_fade = StrategyLogic.check_no_fade(self.market_data)
            
            if confirm_ok and no_fade:
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
                pnl = (exit_price - self.entry_price) * self.shares
                self.trades.append({
                    'symbol': self.symbol,
                    'entry_time': self.entry_time,
                    'exit_time': self.market_data.timestamp,
                    'entry_price': self.entry_price,
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'reason': reason
                })
                self.capital += pnl
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
