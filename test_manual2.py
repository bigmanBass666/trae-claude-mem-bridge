import subprocess
import json
import sys
import time

# Start MCP server
proc = subprocess.Popen(
    [sys.executable, "-u", "d:\\Test\\trae_message_extraction\\trae_claude_mem_bridge\\mcp_server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)

def send_json(obj):
    msg = json.dumps(obj) + "\n"
    proc.stdin.write(msg)
    proc.stdin.flush()
    print(f"Sent: {obj['method'] if 'method' in obj else 'unknown'}")
    return proc.stdout.readline()

# Send initialize
resp = send_json({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
print(f"Initialize resp: {resp}")

# Small delay
time.sleep(0.5)

# Send tools/list
resp = send_json({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
print(f"tools/list resp: {resp[:200] if resp else 'empty'}...")

time.sleep(0.5)

# Send UserPromptSubmit event
resp = send_json({
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
})
print(f"Tool call resp: {resp[:500] if resp else 'empty'}")

proc.stdin.close()
time.sleep(0.5)
proc.terminate()
stdout, stderr = proc.communicate()
print(f"\nStderr:\n{stderr}")
