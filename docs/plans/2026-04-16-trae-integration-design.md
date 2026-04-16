# Trae-Claude-Mem Bridge 项目设计

## 1. 项目目标

**让 Claude-Mem 生态系统支持 Trae IDE，如同它已经支持 Cursor 和 Codex 一样**

- 用户在 Trae 中的工作会话自动被 Claude-Mem 记录
- 用户无需感知桥接器存在，体验如同 Claude-Mem 原生支持 Trae
- 独立插件形式交付，后续可合并到 Claude-Mem 主仓库

---

## 2. 现状评估

### 已完成功能 (v6)

| 功能 | 状态 | 说明 |
|------|------|------|
| Worker 自动检测与启动 | ✅ | 无窗口弹出 |
| 生命周期事件转发 | ✅ | SessionStart/UserPromptSubmit/PostToolUse/Stop/SessionEnd |
| 内部消息过滤 | ✅ | 过滤 `<task-notification>` 等 |
| SKIP_TOOLS 过滤 | ✅ | 减少无效请求 |
| Web UI Trae 卡片 | ✅ | 显示平台标签和时间戳 |
| 多窗口支持 | ✅ | 独立 session 记录 |

### 待完善

- MCP 配置需要用户手动操作（自动化程度可提升）
- 长期稳定性需要实际使用验证
- 错误处理和恢复机制

---

## 3. 架构

```
Trae IDE
    │
    ▼ (MCP stdio protocol)
trae_claude_mem_bridge/
    └── mcp_server.py (v6)
            │
            ▼ (HTTP API)
    Claude-Mem Worker (localhost:37777)
            │
            ▼
    Claude-Mem Database (~/.claude-mem/claude-mem.db)
            │
            ▼
    Web UI (localhost:37777) → Trae 标签页
```

---

## 4. 插件打包计划

### 阶段一：完善与稳定（当前）
- 通过实际使用发现问题并修复
- 完善错误处理和日志
- 优化性能

### 阶段二：插件化打包
- 编写 `plugin.json` 插件清单
- 创建安装脚本/向导
- 一键配置 Trae MCP 设置

### 阶段三：发布与推广
- 整理文档和代码
- 考虑合并到 Claude-Mem 主仓库

---

## 5. Git 提交规范

每完成一次修改，做一次 git 提交。

---

## 6. 测试流程

详见 [claude.md](./claude.md) 中的完整测试流程章节。
