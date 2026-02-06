"""
Real-time Runner for Premarket Strategy with Terminal Dashboard
"""
import time
import os
import logging
import threading
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Optional
import strategy_config as config
from conditions import MarketData, StrategyLogic, Bar
from execution_engine import ExecutionEngine
from tws_data_fetcher import create_tws_data_app

# Configure logging to file only to keep terminal clean for dashboard
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("strategy.log")]
)
logging.getLogger('ibapi').setLevel(logging.WARNING)

class SymbolMonitor:
    def __init__(self, symbol: str, tws_app, executor: ExecutionEngine):
        self.symbol = symbol
        self.tws_app = tws_app
        self.executor = executor
        
        self.bars_1s = deque(maxlen=300)
        self.bars_5s = deque(maxlen=120)
        
        self.curr_1s_data = []
        self.curr_5s_data = []
        self.last_1s_ts = None
        self.last_5s_ts = None
        
        self.state = "WARMUP"
        self.arm_time = None
        self.last_reason = "WARMING_UP"
        self.warmup_start_time = datetime.now()
        
        self.market_data = MarketData(symbol=symbol, price=0.0, timestamp=datetime.now())
        
        # Preload history
        self._preload_history()

    def _preload_history(self):
        """Fetch last few minutes of bars to warm up medians and VWAP."""
        try:
            logging.info(f"[{self.symbol}] Preloading {config.WARMUP_HISTORY_MINUTES}m of history...")
            end_dt = datetime.now()
            duration = f"{config.WARMUP_HISTORY_MINUTES * 60} S"
            
            # Fetch 5s bars
            bars_5s = self.tws_app.fetch_historical_bars(self.symbol, end_dt, duration=duration, bar_size="5 secs")
            for b in bars_5s:
                bar = Bar(b['date'], b['open'], b['high'], b['low'], b['close'], b['volume'], b['average'])
                self.bars_5s.append(bar)
            
            # Fetch 1s bars
            bars_1s = self.tws_app.fetch_historical_bars(self.symbol, end_dt, duration=duration, bar_size="1 secs")
            for b in bars_1s:
                bar = Bar(b['date'], b['open'], b['high'], b['low'], b['close'], b['volume'], b['average'])
                self.bars_1s.append(bar)
                
            logging.info(f"[{self.symbol}] Preloaded {len(self.bars_1s)} 1s-bars and {len(self.bars_5s)} 5s-bars.")
        except Exception as e:
            logging.error(f"[{self.symbol}] History preload failed: {e}. Falling back to time-based warm-up.")

    def on_tick(self, symbol, price, size, vwap, timestamp, bid, ask):
        self.market_data.timestamp = timestamp
        self.market_data.price = price
        self.market_data.volume = size
        self.market_data.vwap = vwap
        self.market_data.bid = bid
        self.market_data.ask = ask
        
        self._update_bars(price, size, vwap, timestamp)

    def on_timer(self):
        """Called periodically to ensure state machine runs even without ticks."""
        now = datetime.now()
        # If we haven't received a tick yet, use current time for timestamp
        if not self.market_data.timestamp or (now - self.market_data.timestamp).total_seconds() > 1.0:
            self.market_data.timestamp = now
            
        # Close current bars if needed based on time
        self._update_bars(self.market_data.price, 0, self.market_data.vwap, now)
        self._process_state_machine()

    def _update_bars(self, price, size, vwap, ts):
        ts_1s = ts.replace(microsecond=0)
        if self.last_1s_ts and ts_1s > self.last_1s_ts:
            if self.curr_1s_data:
                prices = [d[0] for d in self.curr_1s_data]
                vols = [d[1] for d in self.curr_1s_data]
                bar = Bar(self.last_1s_ts, prices[0], max(prices), min(prices), prices[-1], sum(vols), vwap)
                self.bars_1s.append(bar)
                self.curr_1s_data = []
        self.last_1s_ts = ts_1s
        self.curr_1s_data.append((price, size))

        ts_5s = ts.replace(second=(ts.second // 5) * 5, microsecond=0)
        if self.last_5s_ts and ts_5s > self.last_5s_ts:
            if self.curr_5s_data:
                prices = [d[0] for d in self.curr_5s_data]
                vols = [d[1] for d in self.curr_5s_data]
                bar = Bar(self.last_5s_ts, prices[0], max(prices), min(prices), prices[-1], sum(vols), vwap)
                self.bars_5s.append(bar)
                self.curr_5s_data = []
        self.last_5s_ts = ts_5s
        self.curr_5s_data.append((price, size))

    def _process_state_machine(self):
        self.market_data.bars_1s = list(self.bars_1s)
        self.market_data.bars_5s = list(self.bars_5s)
        
        mv1, _, _ = StrategyLogic.calculate_medians(self.market_data.bars_1s, 120)
        mv5, mr5, _ = StrategyLogic.calculate_medians(self.market_data.bars_5s, 120)
        self.market_data.med_vol_1s = mv1
        self.market_data.med_vol_5s = mv5
        self.market_data.med_range_5s = mr5

        # Warm-up check
        if self.state == "WARMUP":
            bars_ok = (len(self.bars_1s) >= config.WARMUP_MIN_1S_BARS and 
                       len(self.bars_5s) >= config.WARMUP_MIN_5S_BARS)
            time_ok = (datetime.now() - self.warmup_start_time).total_seconds() >= config.WARMUP_FALLBACK_SECONDS
            
            if bars_ok or time_ok:
                self.state = "IDLE"
                self.last_reason = "WARMUP_COMPLETE"
                logging.info(f"[{self.symbol}] Warm-up complete. 1s bars: {len(self.bars_1s)}, 5s bars: {len(self.bars_5s)}")
            else:
                return # Still warming up

        pos = self.executor.get_position(self.symbol)
        if pos and pos['status'] == 'IN_TRADE':
            self.state = "IN_TRADE"
        elif not pos:
            if self.state == "ARMED":
                if (datetime.now() - self.arm_time).total_seconds() > config.ARM_TIMEOUT_SECONDS:
                    self.state = "IDLE"
                    self.last_reason = "ARM_TIMEOUT"
            elif self.state != "SUBMITTING" and self.state != "WARMUP":
                self.state = "IDLE"

        if self.state == "IDLE":
            if StrategyLogic.is_in_window(self.market_data.timestamp):
                shock_ok, reason = StrategyLogic.check_shock_1s(self.market_data)
                if shock_ok:
                    self.state = "ARMED"
                    self.arm_time = datetime.now()
                    self.last_reason = "SHOCK"
                    logging.info(f"[{self.symbol}] SHOCK: {reason}")

        elif self.state == "ARMED":
            confirm_ok, c_reason = StrategyLogic.check_confirm_5s(self.market_data)
            safety_ok, s_reason = StrategyLogic.check_exec_safety(self.market_data)
            no_fade = StrategyLogic.check_no_fade(self.market_data)
            
            if confirm_ok and safety_ok and no_fade:
                last_5s = self.market_data.bars_5s[-1]
                med_range = self.market_data.med_range_5s
                stop_dist = max(self.market_data.ask - self.market_data.bid, config.STOP_RANGE_MULT * med_range, self.market_data.price * config.STOP_PCT)
                
                entry_price = self.market_data.ask
                stop_price = entry_price - stop_dist
                R = entry_price - stop_price
                
                success = self.executor.execute_entry(self.symbol, entry_price, stop_price, R)
                if success:
                    self.state = "SUBMITTING"
                    self.last_reason = "CONFIRMED"
                    logging.info(f"[{self.symbol}] ENTRY SUBMITTED: {c_reason}")

        elif self.state == "IN_TRADE":
            pos = self.executor.get_position(self.symbol)
            exit_triggered, reason = StrategyLogic.check_exit(
                self.market_data, pos['actual_entry_price'], pos['stop_price'], pos['entry_time'], pos['R']
            )
            if exit_triggered:
                self.executor.execute_exit(self.symbol, self.market_data.price, reason)
                self.state = "IDLE"
                self.last_reason = f"EXIT_{reason}"

def draw_dashboard(monitors: Dict[str, SymbolMonitor], executor: ExecutionEngine):
    while True:
        try:
            os.system('cls' if os.name == 'nt' else 'clear')
            now_str = datetime.now().strftime("%H:%M:%S")
            print("="*100)
            print(f" PREMARKET SHOCK & CONFIRM STRATEGY | TIME: {now_str}")
            print("="*100)
            
            # STAGE 1: MONITORING
            header = f"{'SYMBOL':<8} | {'PRICE':<7} | {'VWAP':<7} | {'BID/ASK':<13} | {'VOL 1s (MED)':<15} | {'VOL 5s (MED)':<15} | {'STATE':<8} | {'EVENT'}"
            print(header)
            print("-" * len(header))
            for sym in config.WATCHLIST:
                m = monitors.get(sym)
                if not m: continue
                md = m.market_data
                ba = f"{md.bid:.2f}/{md.ask:.2f}"
                
                # Get current bar volumes and medians
                v1 = m.bars_1s[-1].volume if m.bars_1s else 0
                v5 = m.bars_5s[-1].volume if m.bars_5s else 0
                vol1_str = f"{v1:<5.0f} ({md.med_vol_1s:<5.0f})"
                vol5_str = f"{v5:<5.0f} ({md.med_vol_5s:<5.0f})"
                
                print(f"{sym:<8} | {md.price:<7.2f} | {md.vwap:<7.2f} | {ba:<13} | {vol1_str:<15} | {vol5_str:<15} | {m.state:<8} | {m.last_reason}")
            
            # STAGE 2: ACTIVE POSITIONS
            print("\n" + "="*100)
            print(" ACTIVE POSITIONS")
            print("="*100)
            print(f"{'SYMBOL':<8} | {'STATUS':<10} | {'ENTRY':<8} | {'TP':<8} | {'SL':<8} | {'SHARES':<6} | {'PNL':<8} | {'TIME'}")
            print("-" * 100)
            active_any = False
            for sym, pos in executor.positions.items():
                active_any = True
                pnl = (monitors[sym].market_data.price - pos.get('actual_entry_price', pos['entry_price'])) * pos.get('filled_shares', pos['shares'])
                tp = pos.get('actual_entry_price', pos['entry_price']) + config.TP_R_MULT * pos['R']
                time_in = (datetime.now() - pos['entry_time']).total_seconds()
                print(f"{sym:<8} | {pos['status']:<10} | {pos.get('actual_entry_price', 0):<8.2f} | {tp:<8.2f} | {pos['stop_price']:<8.2f} | {pos.get('filled_shares', 0):<6} | {pnl:<8.2f} | {int(time_in)}s")
            if not active_any:
                print(" No active positions.")
	
            # STAGE 3: TRADE HISTORY
            print("\n" + "="*100)
            print(" TRADE HISTORY")
            print("="*100)
            print(f"{'SYMBOL':<8} | {'RESULT':<8} | {'ENTRY':<8} | {'EXIT':<8} | {'PNL':<8} | {'REASON':<12} | {'TIME'}")
            print("-" * 100)
            if not executor.trade_history:
                print(" No completed trades in this session.")
            else:
                for t in executor.trade_history[-5:]: # Show last 5
                    res = "WIN" if t['pnl'] > 0 else "LOSS"
                    print(f"{t['symbol']:<8} | {res:<8} | {t['entry_price']:<8.2f} | {t['exit_price']:<8.2f} | {t['pnl']:<8.2f} | {t['exit_reason']:<12} | {t['time'].strftime('%H:%M:%S')}")
            
            print("="*100)
            time.sleep(1)
        except Exception as e:
            logging.error(f"Dashboard error: {e}")
            time.sleep(1)

def run():
    logging.info("Starting Premarket Strategy Runner...")
    tws_app = create_tws_data_app(host="2.tcp.ngrok.io", port=15861, client_id=777)
    if not tws_app:
        print("[ERROR] Could not connect to TWS.")
        return

    executor = ExecutionEngine(tws_app, config.ACCOUNT_NUMBER)
    monitors = {}
    total = len(config.WATCHLIST)
    print(f"\n[INIT] Preloading history for {total} symbols...")
    for i, symbol in enumerate(config.WATCHLIST, 1):
        print(f"[{i}/{total}] Initializing {symbol}...", end="\r")
        monitors[symbol] = SymbolMonitor(symbol, tws_app, executor)
    print(f"\n[INIT] Preloading complete. Starting market data subscriptions...")

    def create_callback(sym):
        return lambda s, p, v, vw, ts, b, a: monitors[s].on_tick(s, p, v, vw, ts, b, a)

    for symbol in config.WATCHLIST:
        tws_app.subscribe_market_data(symbol, create_callback(symbol))

    # Start dashboard in a separate thread
    dashboard_thread = threading.Thread(target=draw_dashboard, args=(monitors, executor), daemon=True)
    dashboard_thread.start()

    try:
        while True:
            # Run timer-based updates for all monitors
            for m in monitors.values():
                m.on_timer()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping...")
    finally:
        tws_app.disconnect()

if __name__ == "__main__":
    run()
