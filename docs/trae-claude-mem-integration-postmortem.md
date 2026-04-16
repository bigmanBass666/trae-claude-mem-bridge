# 将 Claude-Mem 集成到 Trae：我失败了但总结了这些坑

> **背景**：我在 Claude CLI 中使用 claude-mem 体验非常好，希望能在 Trae 中实现同样的长期记忆功能。这个目标驱使我深入研究了 Claude-Mem 源码和 Trae 的扩展机制，最终发现两者之间存在一个根本性的架构差异。

## 一、目标：像 Cursor/Codex 一样集成 Trae

Claude-Mem 已经在官方支持 Claude CLI 的基础上，额外支持了 Cursor 和 Codex 两个平台。我的目标很明确：**让 claude-mem 也能"认识"Trae**，将其处理范围扩大到 Trae IDE。

初步方案是做一个 MCP 桥接器：
- Trae ↔ MCP Bridge ↔ Claude-Mem Worker
- 让 Trae 的生命周期事件自动流入 claude-mem
- 数据存储和查询复用 claude-mem 原生能力

## 二、Claude-Mem 的架构解析

为了搞清楚集成方式，我深度阅读了 claude-mem v12.1.0 的全部核心源码，包括：

### 2.1 三层架构

```
┌─────────────────────────────────────────┐
│  hooks.json (Claude CLI 调用层)         │  ← 每次事件触发一次
│    ↓ node bun-runner.js                 │
│  bun-runner.js (Bun 启动器)             │  ← 找 Bun、缓冲 stdin
│    ↓ spawn(inner worker)               │
│  worker-wrapper.cjs (生命周期包装器)     │  ← IPC 消息、进程树管理
│    ↓ spawn                            │
│  worker-service.cjs (实际服务)         │  ← HTTP 服务器 :37777
└─────────────────────────────────────────┘
```

### 2.2 Hooks 完整生命周期

从 hooks.json 看，Claude CLI 的每个操作都会触发对应 hooks：

| 顺序 | 事件 | 动作 | 超时 |
|------|------|------|------|
| 1 | **Setup** | 安装/检查依赖 | 300s |
| 2 | **SessionStart** | 启动 Worker → 注入上下文 | 60s |
| 3 | **UserPromptSubmit** | 初始化会话记录 | 60s |
| 4 | **PostToolUse** | 记录工具执行观察 | 120s |
| 5 | **Stop** | 生成会话摘要 | 120s |
| 6 | **SessionEnd** | 标记会话完成 | 30s |

### 2.3 窗口关闭时的行为

**关键发现**：当 Claude CLI 窗口关闭时，**Worker 进程不会关闭**，继续作为守护进程运行。

- Stop hook → 生成摘要
- SessionEnd hook → 标记完成
- Worker 继续监听 :37777 端口

这就是为什么 claude-mem 可以"即开即用"——Worker 是全局常驻的。

## 三、MCP 协议的硬性限制

### 3.1 MCP 协议规范

MCP (Model Context Protocol) 协议本身**不定义任何 session-level lifecycle event**。其生命周期只有三层：

```
Initialization → Operation → Shutdown
```

仅支持的能力：
- `initialize` / `notifications/initialized`
- `tools/list` / `tools/call`
- `logging` / `ping`

### 3.2 Trae 的 MCP 实现

根据 Trae 官方文档，Trae 支持的 MCP 功能同样只有：
- Tools（工具调用）
- Resources（资源）
- Prompts（提示模板）
- Logging（日志）

**没有任何生命周期事件的自动触发机制。**

## 四、Trae vs Claude CLI：关键差异

| 能力 | Trae | Claude Code |
|------|------|-------------|
| **Hooks（确定性自动化）** | ❌ 没有 | ✅ 有 |
| **project_rules.md（提示词级规则）** | ✅ 有 | ✅ 有 |
| **Agent 自定义 system prompt** | ✅ 有 | ✅ 有 |
| **MCP Tools** | ✅ 原生支持 | ✅ 原生支持 |

**Trae 官方文档明确指出：hooks 是 Claude Code 独有的"模型循环之外的确定性自动化"。Trae 没有等价物。**

## 五、我们做的桥接器

尽管如此，我们还是实现了一个功能性的 MCP 桥接器：

### 5.1 架构

```
Trae IDE
  ↓ (手动/MCP tool 调用)
trae_claude_mem_bridge (Python MCP Server)
  ↓ (HTTP API / subprocess hook)
Claude-Mem Worker (:37777)
  ↓
SQLite 数据库 + ChromaDB
```

### 5.2 实现的功能

- ✅ `trae_mem_hook_event` — 接收事件并转发
- ✅ 内部消息过滤（过滤 `<task-notification>` 等）
- ✅ SKIP_TOOLS 客户端过滤
- ✅ `summarize` / `session-complete` 走 HTTP API
- ✅ 平台标识 `platform=trae`
- ✅ Worker 自动检测与启动

### 5.3 日志中的证据

桥接器确实被调用过：

```
2026-04-16 17:49:40 | ERROR | Hook error (UserPromptSubmit/session-init): Worker hook timeout after 30s
```

这说明：
1. 事件确实流入了桥接器
2. 但当时 Worker 没有启动
3. **Trae 的 AI 确实自发调用了我们的 MCP tool**

## 六、替代方案的探索

### 6.1 方案 A：project_rules.md 注入

```markdown
# .trae/rules/project_rules.md

## Claude-Mem 记忆集成

你已集成 claude-mem 长期记忆系统。你必须在以下时机调用 trae_mem_hook_event 工具：

1. 收到用户消息时 → event: UserPromptSubmit
2. 使用任何工具后 → event: PostToolUse  
3. 会话结束时 → event: Stop + SessionEnd

这是硬性要求，不是可选操作。
```

**优点**：对项目内所有对话生效
**缺点**："提示词层面期望"，非 100% 可靠（估计约 80%）

### 6.2 方案 B：专用 Agent

```markdown
# .trae/agents/claude-mem-coder.md
---
name: claude-mem-coder
tools: trae-mem-bridge
---

你是带 claude-mem 记忆增强的开发者。每个操作周期必须：
1. 接收用户输入 → 调用 trae_mem_hook_event(UserPromptSubmit)
2. 执行工具 → 调用 trae_mem_hook_event(PostToolUse)
3. 完成任务前 → 调用 trae_mem_hook_event(Stop) + (SessionEnd)
```

**优点**：更强的约束（独立 system prompt）
**缺点**：需要用户手动切换 Agent

## 七、最终结论

### 7.1 为什么无法实现 100% 自动化

```
Claude CLI hooks:     确定性调用 (hooks 运行在模型循环之外)
Trae + Rules:         概率性遵守 (Rules 只是提示词，AI 可能忽略)
```

这是**架构层面的本质差异**，不是实现细节问题。

### 7.2 现在的状态

- 如果接受约 80% 的可靠性 → 可以通过 `project_rules.md` 实现
- 如果要求 100% 确定性 → 目前无法实现，需要等待 Trae 提供 hooks 或等价机制

### 7.3 这个探索的价值

虽然最终未能实现最初的目标，但这个过程非常有价值：

1. **深度理解了 Claude-Mem 的架构**：三层设计、Worker 守护进程、hooks 生命周期
2. **完整掌握了 Trae 的扩展体系**：Rules、Agents、MCP、Skills 的完整生态
3. **明确了 MCP 协议的边界**：它只是工具调用协议，不是应用生命周期协议

## 八、写给同样想尝试的人

如果你也有类似的想法，希望你能从我的探索中受益：

1. **先读源码再动手** — Claude-Mem 的源码其实很清晰，花一天读完能省很多弯路
2. **区分"协议层"和"实现层"** — MCP 协议不支持的东西，任何 MCP Server 都无法实现
3. **Trae 的 Rules 不是 Hooks** — 提示词层面的规则，AI 可能遵守也可能不遵守
4. **关注 Trae 的更新** — 他们可能在未来加入 hooks 或等价机制

---

> **相关项目**: [Trae-Claude-Mem-Bridge](https://github.com/bigmanBass666/trae-claude-mem-bridge) — 桥接器源码

**如果你最终选择了 project_rules.md 方案并成功实践，欢迎分享经验。这个方向目前还没有人探索过。**

---

*写于 2026-04-16，基于 TraeClaudeMemBridge v6 探索项目*
