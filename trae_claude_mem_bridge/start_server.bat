@echo off
chcp 65001 >nul
echo [trae-mem-bridge] Starting MCP server...
python -u "D:\Test\trae_message_extraction\trae_claude_mem_bridge\mcp_server.py"
