# Premarket Shock & Confirm Momentum Strategy

This repository implements a premarket-only momentum trading strategy for IBKR, designed to trade catalyst bursts around common press-release times.

## Architecture

The strategy uses a **multi-timeframe state machine**:
1.  **IDLE**: Monitors the 1-second layer for a "Shock" (abnormal volume + price surge).
2.  **ARMED**: If a shock is detected within a scheduled time window, the strategy arms itself and waits for "Confirmation" on the 5-second layer.
3.  **IN_TRADE**: If confirmation is received and execution safety gates (spread, quote freshness) pass, an aggressive limit order is placed. Once filled, the strategy manages the exit via multiple conditions (Hard Stop, Weakness, Take Profit, Time Stop).

## Key Components

- `strategy_config.py`: Centralized configuration for all thresholds, time windows, and risk parameters. No "magic numbers" in the logic.
- `conditions.py`: Shared strategy logic used by both real-time trading and backtesting.
- `execution_engine.py`: Handles IBKR order placement with aggressive limit prices, entry timeouts, and state tracking.
- `realtime_runner.py`: Orchestrates live data flow and the strategy state machine.
- `backtest_scanner.py`: Simulates the strategy against historical bars using the same `StrategyLogic`.

## Time Windows (ET)
- 06:59:45 to 07:02:30
- 07:29:45 to 07:32:30
- 07:59:45 to 08:02:30
- 08:29:45 to 08:32:30

## How to Run

### Real-time Trading
```bash
python run_realtime_trading.py
```

### Backtesting
Backtesting requires 1s and 5s bar data. The `backtest_scanner.py` provides the engine to run these simulations.

## Configuration
All parameters can be tuned in `strategy_config.py`. Key parameters include:
- `SHOCK_RET_1S`: Minimum 1s return to trigger shock alarm.
- `CONFIRM_RET_5S`: Minimum 5s return to confirm entry.
- `MAX_SPREAD_PCT`: Maximum allowable bid-ask spread.
- `STOP_PCT`: Hard stop loss percentage.
- `TP_R_MULT`: Take profit target as a multiple of risk (R).
