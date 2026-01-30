"""
Real-time Runner for Premarket Strategy
Handles data aggregation, state machine, and live execution.
"""
import time
import logging
import threading
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Optional
import strategy_config as config
from conditions import MarketData, Bar, StrategyLogic
from execution_engine import ExecutionEngine
from tws_data_fetcher import create_tws_data_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("strategy.log"), logging.StreamHandler()]
)

class SymbolMonitor:
    def __init__(self, symbol: str, tws_app, executor: ExecutionEngine):
        self.symbol = symbol
        self.tws_app = tws_app
        self.executor = executor
        
        # Data buffers
        self.ticks = deque(maxlen=1000)
        self.bars_1s = deque(maxlen=300) # 5 mins of 1s bars
        self.bars_5s = deque(maxlen=120) # 10 mins of 5s bars
        
        # Current bar builders
        self.curr_1s_data = []
        self.curr_5s_data = []
        self.last_1s_ts = None
        self.last_5s_ts = None
        
        # State Machine
        self.state = "IDLE" # IDLE, ARMED, IN_TRADE
        self.arm_time = None
        
        # Market Data Object for conditions
        self.market_data = MarketData(
            symbol=symbol,
            timestamp=datetime.now()
        )

    def on_tick(self, symbol, price, size, vwap, timestamp, bid, ask):
        self.market_data.timestamp = timestamp
        self.market_data.price = price
        self.market_data.volume = size
        self.market_data.vwap = vwap
        self.market_data.bid = bid
        self.market_data.ask = ask
        self.market_data.bid_time = timestamp # Approximation
        self.market_data.ask_time = timestamp
        
        self._update_bars(price, size, vwap, timestamp)
        self._process_state_machine()

    def _update_bars(self, price, size, vwap, ts):
        # 1s Bar Logic
        ts_1s = ts.replace(microsecond=0)
        if self.last_1s_ts and ts_1s > self.last_1s_ts:
            # Close previous 1s bar
            if self.curr_1s_data:
                prices = [d[0] for d in self.curr_1s_data]
                vols = [d[1] for d in self.curr_1s_data]
                bar = Bar(self.last_1s_ts, prices[0], max(prices), min(prices), prices[-1], sum(vols), vwap)
                self.bars_1s.append(bar)
                self.curr_1s_data = []
        self.last_1s_ts = ts_1s
        self.curr_1s_data.append((price, size))

        # 5s Bar Logic
        ts_5s = ts.replace(second=(ts.second // 5) * 5, microsecond=0)
        if self.last_5s_ts and ts_5s > self.last_5s_ts:
            # Close previous 5s bar
            if self.curr_5s_data:
                prices = [d[0] for d in self.curr_5s_data]
                vols = [d[1] for d in self.curr_5s_data]
                bar = Bar(self.last_5s_ts, prices[0], max(prices), min(prices), prices[-1], sum(vols), vwap)
                self.bars_5s.append(bar)
                self.curr_5s_data = []
        self.last_5s_ts = ts_5s
        self.curr_5s_data.append((price, size))

    def _process_state_machine(self):
        # Update MarketData for logic
        self.market_data.bars_1s = list(self.bars_1s)
        self.market_data.bars_5s = list(self.bars_5s)
        
        # Calculate Medians
        mv1, mr1, _ = StrategyLogic.calculate_medians(self.market_data.bars_1s, 120)
        mv5, mr5, _ = StrategyLogic.calculate_medians(self.market_data.bars_5s, 120)
        self.market_data.med_vol_1s = mv1
        self.market_data.med_vol_5s = mv5
        self.market_data.med_range_5s = mr5

        pos = self.executor.get_position(self.symbol)
        if pos and pos['status'] == 'IN_TRADE':
            self.state = "IN_TRADE"
        elif not pos:
            if self.state == "ARMED":
                if (datetime.now() - self.arm_time).total_seconds() > config.ARM_TIMEOUT_SECONDS:
                    self.state = "IDLE"
                    logging.info(f"[{self.symbol}] ARM TIMEOUT -> IDLE")
            else:
                self.state = "IDLE"

        # Logic per state
        if self.state == "IDLE":
            if StrategyLogic.is_in_window(self.market_data.timestamp):
                shock_ok, reason = StrategyLogic.check_shock_1s(self.market_data)
                if shock_ok:
                    self.state = "ARMED"
                    self.arm_time = datetime.now()
                    logging.info(f"[{self.symbol}] SHOCK DETECTED -> ARMED. Reason: {reason}")

        elif self.state == "ARMED":
            confirm_ok, c_reason = StrategyLogic.check_confirm_5s(self.market_data)
            safety_ok, s_reason = StrategyLogic.check_exec_safety(self.market_data)
            no_fade = StrategyLogic.check_no_fade(self.market_data)
            
            if confirm_ok and safety_ok and no_fade:
                # Calculate R and stop
                last_5s = self.market_data.bars_5s[-1]
                med_range = self.market_data.med_range_5s
                stop_dist = max(self.market_data.ask - self.market_data.bid, config.STOP_RANGE_MULT * med_range)
                # Or percent stop
                stop_dist = max(stop_dist, self.market_data.price * config.STOP_PCT)
                
                entry_price = self.market_data.ask
                stop_price = entry_price - stop_dist
                R = entry_price - stop_price
                
                success = self.executor.execute_entry(self.symbol, entry_price, stop_price, R)
                if success:
                    logging.info(f"[{self.symbol}] ALL CONDITIONS MET -> ENTRY SUBMITTED. {c_reason}")
                    self.state = "SUBMITTING"

        elif self.state == "IN_TRADE":
            pos = self.executor.get_position(self.symbol)
            exit_triggered, reason = StrategyLogic.check_exit(
                self.market_data, 
                pos['actual_entry_price'], 
                pos['stop_price'], 
                pos['entry_time'], 
                pos['R']
            )
            if exit_triggered:
                self.executor.execute_exit(self.symbol, self.market_data.price, reason)
                self.state = "IDLE"

def run():
    print("[INIT] Starting Premarket Strategy Runner...")
    tws_app = create_tws_data_app(host="127.0.0.1", port=7497, client_id=777)
    if not tws_app:
        print("[ERROR] Could not connect to TWS.")
        return

    executor = ExecutionEngine(tws_app, config.ACCOUNT_NUMBER)
    monitors = {s: SymbolMonitor(s, tws_app, executor) for s in config.WATCHLIST}

    def create_callback(sym):
        return lambda s, p, v, vw, ts, b, a: monitors[s].on_tick(s, p, v, vw, ts, b, a)

    for symbol in config.WATCHLIST:
        tws_app.subscribe_market_data(symbol, create_callback(symbol))

    try:
        while True:
            # UI or Heartbeat could go here
            time.sleep(1)
    except KeyboardInterrupt:
        print("[INFO] Stopping...")
    finally:
        tws_app.disconnect()

if __name__ == "__main__":
    run()
