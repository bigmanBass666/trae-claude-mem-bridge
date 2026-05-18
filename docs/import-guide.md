# Trae 聊天记录导入 claude-mem 完整指南

## 架构概览

```
Trae IDE
  → workspaceStorage/{hash}/state.vscdb (SQLite, 未加密)
  → 包含: input_history, ChatStore, agent storage, history.entries

claude-mem
  → Worker Service (Bun, port 37700+)
  → ~/.claude-mem/claude-mem.db (SQLite)
  → 6 表 + 3 FTS5 虚拟表
```

## 数据库 Schema

### sdk_sessions (会话表)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| content_session_id | TEXT UNIQUE | 源平台的 session ID |
| memory_session_id | TEXT UNIQUE | claude-mem 内部分配的 UUID |
| project | TEXT | 项目目录名（从文件路径提取） |
| platform_source | TEXT | 平台来源 (claude/codex/trae) |
| user_prompt | TEXT | 首条用户提示 |
| started_at | TEXT | ISO 8601 时间戳 |
| started_at_epoch | INTEGER | Unix 毫秒时间戳 |
| status | TEXT | active/completed/failed |

### observations (观察表 — 核心)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| memory_session_id | TEXT FK | 关联 sdk_sessions |
| project | TEXT | 项目名（必须与 sdk_sessions 一致） |
| type | TEXT | 8 种类型之一 |
| title | TEXT | 简短标题 |
| subtitle | TEXT | 一句话解释 |
| facts | TEXT | JSON 数组 |
| narrative | TEXT | 完整描述 |
| content_hash | TEXT | SHA-256 去重哈希 |
| created_at | TEXT | ISO 8601 |
| created_at_epoch | INTEGER | Unix 毫秒 |

### user_prompts (用户提示表)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| content_session_id | TEXT FK | 关联 sdk_sessions |
| prompt_number | INTEGER | 从 1 开始 |
| prompt_text | TEXT | 用户原始输入 |
| created_at | TEXT | ISO 8601 |
| created_at_epoch | INTEGER | Unix 毫秒 |

### session_summaries (会话摘要表)
需要 AI 回复内容才能生成，Trae 数据中没有。

## Observation 类型

| 类型 | 描述 |
|------|------|
| `bugfix` | 修复 bug |
| `feature` | 新功能 |
| `refactor` | 重构 |
| `change` | 通用修改 |
| `discovery` | 学习/发现 |
| `decision` | 架构决策 |
| `security_alert` | 安全问题 |
| `security_note` | 安全相关 |

## content_hash 算法

```python
import hashlib
def content_hash(memory_session_id, title, narrative):
    return hashlib.sha256(
        f"{memory_session_id or ''}\x00{title or ''}\x00{narrative or ''}".encode()
    ).hexdigest()[:16]
```

## Trae 数据存储结构

### workspaceStorage 目录
```
C:\Users\{user}\AppData\Roaming\Trae CN\User\workspaceStorage\
  {workspace-hash-1}\
    state.vscdb          # 主数据文件
  {workspace-hash-2}\
    state.vscdb
  ...
```

### state.vscdb 中的关键 key

| Key | 内容 | 用途 |
|-----|------|------|
| `icube-ai-agent-storage-input-history` | 用户消息数组 | 提取用户输入 |
| `ChatStore` | 聊天 UI 状态 | 提取时间戳 |
| `memento/icube-ai-agent-storage` | Agent 会话信息 | 获取 sessionId |
| `history.entries` | 编辑器访问历史 | 提取真实项目路径 |

### input_history 格式
```json
[
  {
    "inputText": "用户输入的文本",
    "parsedQuery": ["解析后的查询"],
    "multiMedia": []
  }
]
```
**注意**: 没有时间戳字段。

### ChatStore 时间戳提取
```python
import json
data = json.loads(row[0])
turns = data.get("state", {}).get("turnsHeight", {})
for turn_id in turns.keys():
    oid = turn_id.split("-")[0]
    timestamp = int(oid[:8], 16)  # Unix 秒
```

### history.entries 项目路径提取
```python
from urllib.parse import unquote
entries = json.loads(row[0])
resource = entries[0].get("editor", {}).get("resource", "")
path = unquote(resource).replace("file:///", "")
# 从路径中提取项目名
```

## 导入流程

### 1. 提取数据
- 从 `input_history` 提取用户消息
- 从 `ChatStore` 提取时间戳
- 从 `history.entries` 提取真实项目路径
- 从 `agent storage` 获取 sessionId

### 2. 创建 session
```python
# 通过 Worker hook
payload = {
    "sessionId": session_id,
    "cwd": f"D:/Test/trae-import/{workspace_id}",
    "prompt": first_text[:200],
}
call_worker_hook("session-init", payload)
```

### 3. 创建 observations
```python
# 每条用户消息作为一条 observation
payload = {
    "sessionId": session_id,
    "cwd": f"D:/Test/trae-import/{workspace_id}",
    "toolName": "user_message",
    "toolInput": {"text": text},
    "toolResponse": "",
}
call_worker_hook("observation", payload)
```

### 4. 修复时间戳
Worker hook 创建的 observation 使用 `Date.now()` 作为时间戳。
需要后处理修复为原始聊天时间。

### 5. 修复项目名
Worker hook 使用 `cwd` 的 basename 作为项目名。
需要后处理修复为真实项目名。

## 关键经验教训

### 1. 不要自己编造项目名
- **错误**: 根据消息内容猜测项目名
- **正确**: 从 `history.entries` 的文件路径提取
- **原因**: 文件路径是真实的，内容猜测不可靠

### 2. 不要用文件修改时间当时间戳
- **错误**: `os.path.getmtime()` 作为时间戳
- **正确**: 从 ChatStore 的 ObjectId 提取
- **原因**: 文件修改时间可能与聊天时间相差很远

### 3. 不要用首条消息匹配 session
- **错误**: 通过首条消息内容匹配 workspace
- **正确**: 通过 `agent storage` 的 sessionId 匹配
- **原因**: 不同 workspace 可能有相似的首条消息

### 4. 必须同步更新两个表
- `sdk_sessions.project` 和 `observations.project` 必须一致
- Viewer 显示的是 `observations.project`

### 5. content_hash 必须正确计算
- 去重依赖 `UNIQUE(memory_session_id, content_hash)`
- 错误的 hash 会导致重复数据

## 文件清单

| 文件 | 用途 |
|------|------|
| `import_trae_chats.py` | 主导入脚本 |
| `fix_project_names_final.py` | 修复项目名 |
| `fix_timestamps_final.py` | 修复时间戳 |

## 添加新客户端的步骤

1. **分析数据源**: 找到聊天记录的存储位置和格式
2. **提取关键数据**: 用户消息、时间戳、项目标识
3. **创建导入脚本**: 参考 `import_trae_chats.py`
4. **设置 platform_source**: 使用唯一的平台标识
5. **修复项目名**: 从真实路径提取，不要猜测
6. **修复时间戳**: 从原始数据提取，不要用当前时间
7. **验证**: 在 viewer 中检查数据是否正确显示

## 验证检查清单

- [ ] 所有 session 有有意义的 project 名
- [ ] 所有 observation 的 project 与 session 一致
- [ ] 时间戳在合理范围内（不是导入时间）
- [ ] content_hash 正确计算
- [ ] FTS5 索引包含数据
- [ ] MCP 搜索可以找到数据
- [ ] Viewer 显示正确
