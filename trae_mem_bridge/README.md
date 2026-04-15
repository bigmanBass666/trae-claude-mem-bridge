# Trae-Claude-Mem Bridge

将 Trae IDE 的会话事件桥接到 Claude-Mem Worker API

## 架构

```
Trae IDE ──[stdio/MCP]──▶ bridge_mcp_server.py ──[HTTP]──▶ Claude-Mem Worker (localhost:37777)
```

## MCP 工具列表

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `trae_mem_hook_event` | 接收生命周期事件 | event, payload |
| `search` | 搜索观察记录 | query, limit?, project? |
| `timeline` | 时间线上下文 | observation_id 或 query |
| `get_observations` | 获取详情 | ids (数组或逗号分隔) |
| `inject` | 注入上下文 | project?, limit? |
| `stats` | 统计信息 | 无 |

## 支持的事件类型

- **SessionStart**: 初始化会话 + 注入历史上下文
- **UserPromptSubmit**: 记录用户输入
- **PostToolUse / afterMCPExecution / afterShellExecution / afterFileEdit**: 捕获工具调用
- **Stop**: 生成会话摘要
- **SessionEnd**: 标记会话完成

## 配置位置

- Trae MCP配置: `~/.trae-cn/mcp.json`
- Claude-Mem Worker: `localhost:37777`
- Claude-Mem 数据库: `~/.claude-mem/claude-mem.db`

## 使用方式

在 Trae 中直接调用MCP工具:

1. 记忆搜索: "用search工具搜索authentication相关记录"
2. 手动记录: "用hook_event工具记录这个决策"
3. 查看统计: "用stats工具查看记忆库状态"
