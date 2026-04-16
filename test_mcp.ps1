# 测试 MCP Server
$input = @'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"trae_mem_hook_event","arguments":{"event":"UserPromptSubmit","payload":{"session_id":"test-session-123","cwd":"D:\Test\test-project","prompt":"这是一条测试消息"}}}}
'@
$input | python -u d:\Test\trae_message_extraction\trae_claude_mem_bridge\mcp_server.py
