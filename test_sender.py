import sys
import json

# MCP initialize
print(json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}))
sys.stdout.flush()

# MCP tool call - UserPromptSubmit
print(json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"trae_mem_hook_event","arguments":{"event":"UserPromptSubmit","payload":{"session_id":"manual-test-001","cwd":"D:\\Test\\trae_message_extraction","prompt":"手动测试消息"}}}}))
sys.stdout.flush()
