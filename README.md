# Trae-Claude-Mem

将 Trae IDE 的历史聊天记录导入 [claude-mem](https://github.com/thedotmack/claude-mem) 记忆系统。

## 功能

- 从 Trae 的 database.db（SQLCipher 加密）提取完整对话
- 支持 223+ 个对话、31K+ 条消息的批量导入
- 自动推断项目名、精确时间戳、observation 类型分类
- 导入后可在 claude-mem Web UI 中按 Trae 标签浏览

## 快速开始

```bash
# 1. 确保已解密 database.db 并导出 JSON
# 2. 运行导入
python scripts/import_trae_v2.py

# 3. 打开 Web UI 查看
# http://localhost:37777 → 点击 Trae 标签
```

## 文档

- [导入完整指南](docs/import-guide.md) — 架构、schema、踩坑总结、添加新客户端步骤
- [项目时间线](docs/journey-into-claude-mem-trae.md) — Journey Into claude-mem-trae

## 许可

MIT
