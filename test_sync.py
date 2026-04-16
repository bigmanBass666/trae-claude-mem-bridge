import subprocess
import json
import sys
import time

proc = subprocess.Popen(
    [sys.executable, "-u", "d:\\Test\\trae_message_extraction\\trae_claude_mem_bridge\\mcp_server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)

pending_requests = {}

def send_and_wait(obj, timeout=30):
    req_id = obj.get("id")
    msg = json.dumps(obj) + "\n"
    proc.stdin.write(msg)
    proc.stdin.flush()
    print(f"Sent: {obj.get('method', 'unknown')} (id={req_id})")

    start = time.time()
    while time.time() - start < timeout:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            resp = json.loads(line)
            if resp.get("id") == req_id:
                return resp
        except:
            pass
    return None

# Initialize (no waiting for worker)
resp = send_and_wait({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}, timeout=60)
print(f"Initialize resp: {resp}")

# Now worker should be ready, send tools/list
resp = send_and_wait({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}, timeout=10)
print(f"tools/list resp received, tools count: {len(resp.get('result', {}).get('tools', [])) if resp else 'None'}")

# Send UserPromptSubmit
resp = send_and_wait({
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
        "name":"trae_mem_hook_event",
        "arguments":{
            "event":"UserPromptSubmit",
            "payload":{
                "session_id":"manual-test-001",
                "cwd":"D:\\Test\\trae_message_extraction",
                "prompt":"手动测试消息"
            }
        }
    }
}, timeout=15)
print(f"UserPromptSubmit resp: {resp}")

proc.stdin.close()
proc.terminate()
stdout, stderr = proc.communicate(timeout=5)
print(f"\nStderr:\n{stderr[:2000]}")
