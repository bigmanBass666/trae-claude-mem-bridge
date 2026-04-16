# Trae-Claude-Mem Bridge

将 Trae IDE 会话桥接到 Claude-Mem 记忆系统。

## 项目目标

让 Claude-Mem 生态系统支持 Trae IDE，如同支持 Cursor 和 Codex 一样。

- 独立插件形式交付
- 全自动化，用户无感知
- 后续可合并到 Claude-Mem 主仓库

## 架构

```
Trae IDE → MCP Bridge → Claude-Mem Worker → Database → Web UI
```

## 核心文件

| 文件 | 说明 |
|------|------|
| `trae_claude_mem_bridge/mcp_server.py` | MCP Server v6 |
| `trae_claude_mem_bridge/start_server.bat` | 启动脚本 |
| `docs/plans/` | 项目设计文档 |
| `docs/test-procedure.md` | 测试流程 |

## 当前版本

v6: Worker 自动检测与启动，无窗口弹出

## Git 规范

每完成一次修改，做一次 git 提交。
