import subprocess
import json
import sys

# Start MCP server
proc = subprocess.Popen(
    [sys.executable, "-u", "d:\\Test\\trae_message_extraction\\trae_claude_mem_bridge\\mcp_server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# Send initialize
init_msg = json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}) + "\n"
proc.stdin.write(init_msg)
proc.stdin.flush()

# Read response
resp1 = proc.stdout.readline()
print(f"Initialize response: {resp1}")

# Send UserPromptSubmit event
tool_msg = json.dumps({
    "jsonrpc":"2.0",
    "id":2,
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
}) + "\n"
proc.stdin.write(tool_msg)
proc.stdin.flush()

# Read response
resp2 = proc.stdout.readline()
print(f"Tool call response: {resp2}")

# Send SessionEnd
end_msg = json.dumps({
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
        "name":"trae_mem_hook_event",
        "arguments":{
            "event":"SessionEnd",
            "payload":{
                "session_id":"manual-test-001",
                "cwd":"D:\\Test\\trae_message_extraction"
            }
        }
    }
}) + "\n"
proc.stdin.write(end_msg)
proc.stdin.flush()

resp3 = proc.stdout.readline()
print(f"SessionEnd response: {resp3}")

proc.stdin.close()
proc.wait()

# Show stderr
stderr_output = proc.stderr.read()
print(f"\nStderr:\n{stderr_output}")
