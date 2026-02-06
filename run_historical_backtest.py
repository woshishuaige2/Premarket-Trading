"""
Runner for Historical Backtesting using IBKR TWS Data.
Usage: python run_historical_backtest.py --symbols MOVE,BNAI --date 2026-01-28
"""
import argparse
import logging
from datetime import datetime
from tws_data_fetcher import create_tws_data_app
from backtest_scanner import BacktestEngine, run_backtest
import strategy_config as config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
# Suppress verbose IBKR internal logging
logging.getLogger('ibapi').setLevel(logging.WARNING)

def main():
    parser = argparse.ArgumentParser(description='Premarket Strategy Historical Backtester')
    parser.add_argument('--symbols', type=str, help='Comma-separated symbols, e.g., MOVE,BNAI', default=",".join(config.WATCHLIST))
    parser.add_argument('--date', type=str, help='Date in YYYY-MM-DD format', default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument('--host', type=str, default="2.tcp.ngrok.io", help='TWS host')
    parser.add_argument('--port', type=int, default=15861, help='TWS port')
    
    args = parser.parse_args()
    symbols = [s.strip() for s in args.symbols.split(',')]
    
    print("="*65)
    print(" PREMARKET STRATEGY HISTORICAL BACKTEST")
    print("="*65)
    print(f" DATE: {args.date}")
    print(f" SYMBOLS: {', '.join(symbols)}")
    print("="*65)

    tws_app = create_tws_data_app(host=args.host, port=args.port, client_id=666)
    if not tws_app:
        print("[ERROR] Could not connect to TWS.")
        return

    try:
        for symbol in symbols:
            engine = BacktestEngine(symbol)
            bars_1s, bars_5s = engine.load_tws_data(tws_app, args.date)
            
            if not bars_1s or not bars_5s:
                print(f"[SKIP] Insufficient data for {symbol} on {args.date} (1s: {len(bars_1s)}, 5s: {len(bars_5s)})")
                continue
                
            print(f"[RUN] Simulating {symbol} with {len(bars_1s)} 1s-bars and {len(bars_5s)} 5s-bars...")
            trades, final_capital = run_backtest(symbol, bars_1s, bars_5s)
            
            if not trades:
                print(f"[RESULT] {symbol}: No trades triggered.")
            else:
                print(f"\n[TRADES] {symbol}:")
                print(f"{'ENTRY TIME':<20} | {'EXIT TIME':<20} | {'SHARES':<7} | {'ENTRY':<8} | {'EXIT':<8} | {'GROSS $':<9} | {'COMM $':<8} | {'NET $':<9} | {'NET %':<8} | {'REASON'}")
                print("-" * 130)
                for t in trades:
                    e_time = t['entry_time'].strftime("%H:%M:%S")
                    x_time = t['exit_time'].strftime("%H:%M:%S")
                    print(f"{e_time:<20} | {x_time:<20} | {t['shares']:<7} | {t['entry_price']:<8.2f} | {t['exit_price']:<8.2f} | {t['gross_pnl']:<9.2f} | {t['commission']:<8.2f} | {t['pnl']:<9.2f} | {t['pnl_pct']:<7.2f}% | {t['reason']}")
                
                total_gross_pnl = sum(t['gross_pnl'] for t in trades)
                total_commission = sum(t['commission'] for t in trades)
                total_net_pnl = sum(t['pnl'] for t in trades)
                total_investment = sum(t['investment'] for t in trades)
                avg_pnl_pct = (total_net_pnl / total_investment * 100) if total_investment > 0 else 0
                print(f"\n[SUMMARY] {symbol} Gross PnL: ${total_gross_pnl:.2f} | Commission: ${total_commission:.2f} | Net PnL: ${total_net_pnl:.2f} ({avg_pnl_pct:+.2f}%) | Final Capital: ${final_capital:.2f}\n")

    finally:
        tws_app.disconnect()
        print("[INFO] Backtest complete.")

if __name__ == "__main__":
    main()
