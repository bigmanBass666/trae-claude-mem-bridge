# Trae-Claude-Mem Bridge

将 Trae IDE 会话桥接到 Claude-Mem 长期记忆系统。

## ⚠️ 项目状态：探索性研究

这是一个**技术复盘项目**，而非可用的最终产品。

**核心结论**：由于 Trae 与 Claude CLI 的架构差异（Trae 没有 Hooks 系统），目前无法实现 100% 自动化的记忆集成。详细分析请参阅：

**[📄 完整复盘文章](./docs/trae-claude-mem-integration-postmortem.md)**

## 架构

```
Trae IDE ──[MCP]──▶ trae_claude_mem_bridge ──[HTTP]──▶ Claude-Mem Worker (:37777)
```

## 快速开始

### 前置要求

- [Claude-Mem](https://github.com/thedotmack/claude-mem) 已安装并运行
- Bun runtime (`bun --version`)
- Python 3.8+

### 配置

1. 克隆本仓库
2. 配置 Trae MCP：

```json
{
  "mcpServers": {
    "trae-claude-mem-bridge": {
      "command": "python",
      "args": ["-u", "trae_claude_mem_bridge/mcp_server.py"]
    }
  }
}
```

3. 重启 Trae

### 验证

```bash
curl http://localhost:37777
```

## MCP 工具

| 工具 | 功能 |
|------|------|
| `trae_mem_hook_event` | 接收生命周期事件 |

## 目录结构

```
├── trae_claude_mem_bridge/
│   ├── mcp_server.py      # MCP Server 实现
│   └── README.md          # 子模块说明
├── docs/
│   ├── trae-claude-mem-integration-postmortem.md  # 完整复盘
│   ├── test-procedure.md   # 测试流程
│   └── plans/             # 设计文档
└── claude.md              # Claude Code 项目说明
```

## 为什么无法实现全自动？

| 能力 | Claude CLI | Trae |
|------|-----------|------|
| Hooks（确定性自动化） | ✅ | ❌ |
| Rules（提示词规则） | ✅ | ✅ |

Trae 的 Rules 只是提示词层面的约束（非 100% 可靠），而 Claude CLI 的 Hooks 运行在模型循环之外。

## 参考链接

- [Claude-Mem 源码分析](./docs/trae-claude-mem-integration-postmortem.md)
- [Claude-Mem 官方](https://github.com/thedotmack/claude-mem)
- [Trae 官方文档](https://docs.trae.ai)

---

*本项目仅供技术探索和参考*
