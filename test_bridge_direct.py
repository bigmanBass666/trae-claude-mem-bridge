import subprocess, json

proc = subprocess.Popen(
    ["python", "-u", r"D:\Test\trae_message_extraction\trae_mem_bridge\mcp_server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)

import threading, queue

def read_stdout(out, q):
    for line in iter(out.readline, ""):
        q.put(line)
    out.close()

q = queue.Queue()
t = threading.Thread(target=read_stdout, args=(proc.stdout, q))
t.daemon = True
t.start()

def send(msg):
    line = json.dumps(msg)
    proc.stdin.write(line + "\n")
    proc.stdin.flush()

def recv(timeout=5):
    try:
        line = q.get(timeout=timeout)
        return json.loads(line)
    except queue.Empty:
        return {"error": "timeout"}

print("=== MCP Bridge v6 Test ===")

# 1. Initialize
send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}})
print("1. Initialize:", recv())

# 2. Tools list
send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
print("2. Tools list:", recv())

# 3. Send hook event
send({"jsonrpc": "2.0", "id": 3, "method": "notifications/initialized", "params": {}})

send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "trae_mem_hook_event", "arguments": {"event": "SessionStart", "payload": {"session_id": "TEST-V6-DIRECT", "cwd": "D:/Test/trae_message_extraction"}}}})
print("3. Hook event (SessionStart):", recv(timeout=15))

print("=== Done ===")
proc.terminate()
