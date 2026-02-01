"""
Premarket Shock & Confirm Momentum Strategy - Configuration
All thresholds and parameters are defined here as global constants.
"""

# =============================================================================
# TIME WINDOWS (US/Eastern)
# =============================================================================
PREMARKET_WINDOWS = [
    ("04:00:00", "09:30:00") # Loosened for testing: Full premarket
]

# =============================================================================
# EXECUTION SAFETY GATE
# =============================================================================
MAX_SPREAD_PCT = 10.0           # Loosened: 10% absolute cap
SPREAD_REL_MULT = 1.0           # Loosened: 100% of 5s move
QUOTE_STALE_MS = 5000           # Loosened: 5s stale

# =============================================================================
# LAYER A: SHOCK DETECTOR (1 second)
# =============================================================================
SHOCK_RET_1S = 0.005            # Loosened: +0.5% (was 3%)
SHOCK_VOL_MULT_1S = 1.0         # Loosened: 1x median (was 3x)

# =============================================================================
# LAYER B: CONTINUATION CONFIRM (5 seconds)
# =============================================================================
CONFIRM_RET_5S = 0.005          # Loosened: +0.5% (was 4%)
CONFIRM_VOL_MULT_5S = 1.0       # Loosened: 1x median (was 2x)
RANGE_MULT_5S = 1.0             # Loosened: 1x median (was 2x)

# =============================================================================
# NO-INSTANT-FADE FILTER
# =============================================================================
NO_FADE_FRAC = 0.5              # Loosened: 50% range (was 25%)

# =============================================================================
# ORDER PLACEMENT
# =============================================================================
ENTRY_OFFSET = 0.01             # +$0.01 offset for aggressive limit
ENTRY_TIMEOUT_MS = 500          # 300ms to 800ms
PARTIAL_FILL_RULE = "CANCEL"    # "CANCEL" (Option A) or "REPRICE" (Option B)

# =============================================================================
# RISK MANAGEMENT
# =============================================================================
STOP_PCT = 0.05                 # Loosened: 5% stop
STOP_RANGE_MULT = 1.0           # Loosened
TP_R_MULT = 1.0                 # Target profit as multiple of R
FAIL_RET_1S = 0.05              # Loosened

# TIME STOP
TIME_STOP_SECONDS = 60          # Loosened
MIN_PNL_AT_TIME = -1.0          # Loosened: effectively disabled

# =============================================================================
# KILL SWITCHES
# =============================================================================
MAX_CONSECUTIVE_LOSSES = 10     # Loosened
REGIME_RISK_OFF_RET_30S = -0.20 # Loosened

# =============================================================================
# STATE MACHINE
# =============================================================================
ARM_TIMEOUT_SECONDS = 10.0      # Loosened

# =============================================================================
# TRADING PARAMETERS
# =============================================================================
INVESTMENT_PER_TRADE = 1000.0
ACCOUNT_NUMBER = "DUO200259"
WATCHLIST = ["RPGL"]
