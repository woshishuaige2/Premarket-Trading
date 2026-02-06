"""
Premarket Shock & Confirm Momentum Strategy - Configuration
All thresholds and parameters are defined here as global constants.
"""

# =============================================================================
# TIME WINDOWS (US/Eastern)
# =============================================================================
PREMARKET_WINDOWS = [
    ("07:00:00", "08:30:00")
]

# =============================================================================
# EXECUTION SAFETY GATE
# =============================================================================
MAX_SPREAD_PCT = 1.0            # 1% max spread
SPREAD_REL_MULT = 0.5           # Spread must be < 50% of the 5s move
QUOTE_STALE_MS = 2000           # 2s freshness

# =============================================================================
# LAYER A: SHOCK DETECTOR (1-second OR 2-second alternative)
# =============================================================================
SHOCK_RET_1S = 0.03             # 3% shock
SHOCK_VOL_MULT_1S = 3.0         # 3x median

SHOCK_RET_2S = 0.05             # 5% shock over 2s
SHOCK_VOL_MULT_2S = 5.0         # 5x median

# =============================================================================
# LAYER B: CONTINUATION CONFIRM (5 seconds)
# =============================================================================
CONFIRM_RET_5S = 0.04           # 4% confirm
CONFIRM_VOL_MULT_5S = 2.0       # 2x median
RANGE_MULT_5S = 2.0            # 2x median range

# =============================================================================
# NO-INSTANT-FADE FILTER
# =============================================================================
NO_FADE_FRAC = 0.20             # Must hold top 80% of the 5s range

# =============================================================================
# ORDER PLACEMENT
# =============================================================================
ENTRY_OFFSET = 0.00             # 0 offset for aggressive limit (market-like)
ENTRY_TIMEOUT_MS = 300000       # 5 minutes timeout for testing
PARTIAL_FILL_RULE = "CANCEL"

# =============================================================================
# RISK MANAGEMENT
# =============================================================================
STOP_PCT = 0.015                # 1.5% hard stop
STOP_RANGE_MULT = 2.0           # or 2x median 5s range
TP_R_MULT = 3.0                 # 3R target
FAIL_RET_1S = 0.02              # Exit if 1s bar drops 2%

# TIME STOP
TIME_STOP_SECONDS = 300         # 5 minutes
MIN_PNL_AT_TIME = 0.5           # Must be up 0.5R at 5 mins

# =============================================================================
# KILL SWITCHES
# =============================================================================
MAX_CONSECUTIVE_LOSSES = 100
REGIME_RISK_OFF_RET_30S = -0.99 # Disabled

# =============================================================================
# STATE MACHINE
# =============================================================================
ARM_TIMEOUT_SECONDS = 300.0

# =============================================================================
# TRADING PARAMETERS
# =============================================================================
INVESTMENT_PER_TRADE = 100.0
ACCOUNT_NUMBER = "DUO200259"     # Replace with actual IBKR account
WATCHLIST = ["UOKA", "TNON", "IOBT", "WNW", "EDHL"]

# =============================================================================
# COMMISSION STRUCTURE (IBKR)
# =============================================================================
COMMISSION_PER_SHARE = 0.005
COMMISSION_MIN = 1.0
COMMISSION_PERCENT_LOW = 0.005

# =============================================================================
# BACKTEST DATA SETTINGS
# =============================================================================
BACKTEST_1S_WHAT_TO_SHOW = "TRADES"

# =============================================================================
# DEBUG SETTINGS
# =============================================================================
DEBUG_TIME_WINDOW = None
BYPASS_VWAP_CHECK = True
BYPASS_TIME_WINDOW = True

# =============================================================================
# WARM-UP SETTINGS
# =============================================================================
WARMUP_MIN_1S_BARS = 120        # 2 mins of data
WARMUP_MIN_5S_BARS = 24         # 2 mins of data
WARMUP_HISTORY_MINUTES = 5      # 5 min preload
WARMUP_FALLBACK_SECONDS = 60    # 1 min fallback
