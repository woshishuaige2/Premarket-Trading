"""
Quick TWS Connection Diagnostic Tool
Tests common TWS/IB Gateway ports
"""
import socket
from tws_data_fetcher import create_tws_data_app

# Common IBKR API ports
PORTS_TO_TEST = {
    7497: "TWS Paper Trading",
    7496: "TWS Live Trading", 
    4002: "IB Gateway Paper Trading",
    4001: "IB Gateway Live Trading"
}

print("="*60)
print("TWS/IB Gateway Connection Diagnostic")
print("="*60)

# Step 1: Check if ports are listening
print("\n1. Checking which ports are open...")
open_ports = []
for port, desc in PORTS_TO_TEST.items():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    
    if result == 0:
        print(f"   ✓ Port {port} is OPEN ({desc})")
        open_ports.append(port)
    else:
        print(f"   ✗ Port {port} is CLOSED ({desc})")

if not open_ports:
    print("\n❌ NO PORTS ARE OPEN!")
    print("\nPossible issues:")
    print("  - TWS or IB Gateway is not running")
    print("  - API connections are not enabled in TWS")
    print("\nTo fix:")
    print("  1. Open TWS or IB Gateway")
    print("  2. Go to: File -> Global Configuration -> API -> Settings")
    print("  3. Check 'Enable ActiveX and Socket Clients'")
    print("  4. Note the 'Socket port' number")
    print("  5. Click OK and restart TWS")
    exit(1)

# Step 2: Try to connect to open ports
print(f"\n2. Testing API connection on open ports...")
for port in open_ports:
    print(f"\n   Testing {port} ({PORTS_TO_TEST[port]})...")
    app = create_tws_data_app(host="127.0.0.1", port=port, client_id=999)
    if app:
        print(f"   ✓ Successfully connected on port {port}!")
        print(f"\n✅ Use port {port} in your script")
        app.disconnect()
        break
    else:
        print(f"   ✗ Connection failed on port {port}")
else:
    print("\n❌ Could not connect to any open port")
    print("\nPossible issues:")
    print("  - Client ID 999 might not be whitelisted")
    print("  - 'Enable ActiveX and Socket Clients' might not be checked")
    print("  - TWS might not have accepted the API connection request")
    print("\nCheck TWS settings:")
    print("  File -> Global Configuration -> API -> Settings")
    print("  - Enable ActiveX and Socket Clients: ✓")
    print("  - Read-Only API: ✗ (unchecked)")
    print("  - Trusted IPs: leave blank or add 127.0.0.1")

print("\n" + "="*60)
