"""
Premarket Shock & Confirm Momentum Strategy - Configuration
All thresholds and parameters are defined here as global constants.
"""

# =============================================================================
# TIME WINDOWS (US/Eastern)
# =============================================================================
PREMARKET_WINDOWS = [
    ("06:59:45", "07:02:30"),
    ("07:29:45", "07:32:30"),
    ("07:59:45", "08:02:30"),
    ("08:29:45", "08:32:30")
]

# =============================================================================
# EXECUTION SAFETY GATE
# =============================================================================
MAX_SPREAD_PCT = 2.5            # Absolute cap: 1.5% to 3.0%
SPREAD_REL_MULT = 0.25          # Spread must be <= 25% of the 5s move magnitude
QUOTE_STALE_MS = 1000           # Max age of bid/ask quote in ms

# =============================================================================
# LAYER A: SHOCK DETECTOR (1 second)
# =============================================================================
SHOCK_RET_1S = 0.03             # +3% to +5% (0.03 = 3%)
SHOCK_VOL_MULT_1S = 3.0         # vol_1s >= 3x median_vol_1s

# =============================================================================
# LAYER B: CONTINUATION CONFIRM (5 seconds)
# =============================================================================
CONFIRM_RET_5S = 0.04           # +4% to +8%
CONFIRM_VOL_MULT_5S = 2.0       # vol_5s >= 2x median_vol_5s
RANGE_MULT_5S = 2.0             # range_5s >= 2x median_range_5s

# =============================================================================
# NO-INSTANT-FADE FILTER
# =============================================================================
NO_FADE_FRAC = 0.25             # Must hold within top 25% of 5s range

# =============================================================================
# ORDER PLACEMENT
# =============================================================================
ENTRY_OFFSET = 0.01             # +$0.01 offset for aggressive limit
ENTRY_TIMEOUT_MS = 500          # 300ms to 800ms
PARTIAL_FILL_RULE = "CANCEL"    # "CANCEL" (Option A) or "REPRICE" (Option B)

# =============================================================================
# RISK MANAGEMENT
# =============================================================================
STOP_PCT = 0.015                # 0.8% to 2.0% (0.015 = 1.5%)
STOP_RANGE_MULT = 0.5           # Multiplier for median_range_5s
TP_R_MULT = 1.0                 # Target profit as multiple of R
FAIL_RET_1S = 0.02              # -2% sudden drop exit

# TIME STOP
TIME_STOP_SECONDS = 20
MIN_PNL_AT_TIME = 0.2           # +0.2R required after TIME_STOP_SECONDS

# =============================================================================
# KILL SWITCHES
# =============================================================================
MAX_CONSECUTIVE_LOSSES = 2
REGIME_RISK_OFF_RET_30S = -0.05 # -5% drop in 30s triggers kill switch

# =============================================================================
# STATE MACHINE
# =============================================================================
ARM_TIMEOUT_SECONDS = 3.0

# =============================================================================
# TRADING PARAMETERS
# =============================================================================
INVESTMENT_PER_TRADE = 1000.0
ACCOUNT_NUMBER = "DUO200259"     # Replace with actual IBKR account
WATCHLIST = ["TWNP", "PMN"]
