"""
Premarket Shock & Confirm Momentum Strategy - Configuration
All thresholds and parameters are defined here as global constants.
"""

# =============================================================================
# TIME WINDOWS (US/Eastern)
# =============================================================================
PREMARKET_WINDOWS = [
    ("00:00:00", "23:59:59") # Full 24h for testing
]

# =============================================================================
# EXECUTION SAFETY GATE
# =============================================================================
MAX_SPREAD_PCT = 50.0           # 50% spread allowed for testing
SPREAD_REL_MULT = 100.0         # Disabled
QUOTE_STALE_MS = 10000          # 10s freshness

# =============================================================================
# LAYER A: SHOCK DETECTOR (1-second OR 2-second alternative)
# =============================================================================
SHOCK_RET_1S = 0.0001           # 0.01% - Trigger on almost any move
SHOCK_VOL_MULT_1S = 0.1         # 10% of median

SHOCK_RET_2S = 0.0001
SHOCK_VOL_MULT_2S = 0.1

# =============================================================================
# LAYER B: CONTINUATION CONFIRM (5 seconds)
# =============================================================================
CONFIRM_RET_5S = 0.0001         # 0.01%
CONFIRM_VOL_MULT_5S = 0.1
RANGE_MULT_5S = 0.1

# =============================================================================
# NO-INSTANT-FADE FILTER
# =============================================================================
NO_FADE_FRAC = 0.99             # Allow almost any pullback

# =============================================================================
# ORDER PLACEMENT
# =============================================================================
ENTRY_OFFSET = 0.10             # $0.10 offset for aggressive limit
ENTRY_TIMEOUT_MS = 5000         # 5s timeout
PARTIAL_FILL_RULE = "CANCEL"

# =============================================================================
# RISK MANAGEMENT
# =============================================================================
STOP_PCT = 0.50                 # 50% stop
STOP_RANGE_MULT = 0.0
TP_R_MULT = 10.0                # 10R target
FAIL_RET_1S = 0.50              # Disabled

# TIME STOP
TIME_STOP_SECONDS = 3600        # 1 hour
MIN_PNL_AT_TIME = -10.0         # Disabled

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

# =============================================================================
# WARM-UP SETTINGS
# =============================================================================
WARMUP_MIN_1S_BARS = 5          # Only 5 bars needed
WARMUP_MIN_5S_BARS = 1          # Only 1 bar needed
WARMUP_HISTORY_MINUTES = 1      # Only 1 min preload
WARMUP_FALLBACK_SECONDS = 10    # 10s fallback
