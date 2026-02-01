from datetime import datetime, timedelta
from conditions import StrategyLogic, MarketData, Bar
import strategy_config as config

def debug_fat_entry():
    print("=== DEBUGGING FAT ENTRY AT 09:16:30 ===")
    
    # 1. Setup Market Data
    now = datetime(2026, 1, 30, 9, 16, 30)
    data = MarketData(symbol="FAT", timestamp=now, price=0.4200)
    
    # Setup Medians (Loosened as per config)
    data.med_vol_1s = 1000
    data.med_vol_5s = 5000
    data.med_range_5s = 0.01
    
    # 2. Simulate the SHOCK (1s layer)
    # The 5s bar shows 0.3951 -> 0.4200. Let's assume the shock happened in the first second.
    shock_bar = Bar(now - timedelta(seconds=4), 0.3951, 0.4050, 0.3951, 0.4050, 15000)
    data.bars_1s = [shock_bar]
    
    shock_ok, s_reason = StrategyLogic.check_shock_1s(data)
    print(f"Step 1: Shock Check -> {shock_ok} ({s_reason})")
    
    # 3. Simulate the CONFIRM (5s layer)
    # 0.3951 to 0.4200 is +6.3%
    confirm_bar = Bar(now, 0.3951, 0.4200, 0.3951, 0.4200, 74810) # 74.81K vol from screenshot
    data.bars_5s = [confirm_bar]
    
    confirm_ok, c_reason = StrategyLogic.check_confirm_5s(data)
    print(f"Step 2: Confirm Check -> {confirm_ok} ({c_reason})")
    
    # 4. Check No-Fade Filter
    # Price is 0.4200, High is 0.4200. This should pass.
    no_fade = StrategyLogic.check_no_fade(data)
    print(f"Step 3: No-Fade Check -> {no_fade}")
    
    # 5. Check Execution Safety
    data.bid = 0.4190
    data.ask = 0.4210
    data.bid_time = now
    data.ask_time = now
    safety_ok, saf_reason = StrategyLogic.check_exec_safety(data)
    print(f"Step 4: Safety Check -> {safety_ok} ({saf_reason})")
    
    # 6. Check Time Window
    window_ok = StrategyLogic.is_in_window(now)
    print(f"Step 5: Window Check -> {window_ok}")

if __name__ == "__main__":
    debug_fat_entry()
