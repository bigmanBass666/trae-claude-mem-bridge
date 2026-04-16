import urllib.request
import socket

print("Testing connection to Worker on port 37777...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    result = sock.connect_ex(('127.0.0.1', 37777))
    sock.close()
    if result == 0:
        print("Port 37777 is OPEN and ACCEPTING connections")
    else:
        print(f"Port 37777 is NOT accessible (connect_ex returned {result})")
except Exception as e:
    print(f"Socket error: {e}")

print("\nTrying HTTP request...")
try:
    req = urllib.request.urlopen("http://localhost:37777/health", timeout=10)
    print(f"Response: {req.read().decode()}")
except Exception as e:
    print(f"HTTP error: {e}")
