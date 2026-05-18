# Trae-Claude-Mem

将 Trae IDE 的历史聊天记录导入 Claude-Mem 记忆系统。

## 项目目标

让 Claude-Mem 支持 Trae 平台，如同支持 Cursor 和 Codex 一样。

## 架构

```
Trae database.db (SQLCipher 加密)
  → 解密导出 trae_full_data.json
  → import_trae_v2.py (直接写入 SQLite)
  → ~/.claude-mem/claude-mem.db
  → Web UI (localhost:37777)
```

## 核心文件

| 文件 | 说明 |
|------|------|
| `scripts/import_trae_v2.py` | **主导入脚本**（基于解密的 database.db） |
| `scripts/trae_project_map.json` | 项目名映射配置（可手动覆盖） |
| `docs/import-guide.md` | 导入完整指南（schema、踩坑总结、添加新客户端步骤） |
| `docs/journey-into-claude-mem-trae.md` | 项目时间线分析报告 |

## 数据源

- **主数据**: `D:/Test/claude_test/subagent_test/trae_db_export/trae_full_data.json`
  - 223 个对话，31,438 条消息，16 个项目
  - 含完整用户+AI对话，精确时间戳
- **解密密钥**: `D:/Test/claude_test/subagent_test/trae_db_export/decrypted_key.json`
- **原始数据库**: `C:/Users/86150/AppData/Roaming/Trae CN/ModularData/ai-agent/database.db`

## 使用方法

```bash
# 干跑验证
python scripts/import_trae_v2.py --dry-run

# 执行导入
python scripts/import_trae_v2.py

# 指定数据源
python scripts/import_trae_v2.py --source /path/to/trae_full_data.json
```

## 项目结构

```
scripts/                   # 导入脚本
docs/                      # 文档和报告
trae_claude_mem_bridge/    # [已废弃] MCP Bridge 代码
screenshots/               # 截图（不纳入 git）
```

## 已废弃

- `trae_claude_mem_bridge/` — MCP Bridge 方案已废弃，改用批量导入
- `scripts/import_trae_chats.py` — v1 导入脚本（从 state.vscdb），已被 v2 替代
- `scripts/fix_*.py` — v1 修复脚本，已被 v2 整合

## Git 规范

每完成一次修改，做一次 git 提交。
