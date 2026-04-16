# Trae-Claude-Mem Bridge v6 测试流程

本文档详细描述 Trae-Claude-Mem Bridge v6 的完整测试流程，用于验证所有功能正常工作。

---

## 1. 基础环境检查

### 1.1 文件结构检查
```
d:\Test\trae_message_extraction\
├── trae_claude_mem_bridge/
│   ├── mcp_server.py      # v6 主文件
│   ├── start_server.bat    # 启动脚本
│   └── README.md
├── .gitignore
├── docs/
│   ├── plans/
│   └── test-procedure.md   # 本文档
└── extract_trae_chats.py   # 提取脚本
```

### 1.2 版本验证
```bash
head -20 trae_claude_mem_bridge/mcp_server.py
```
确认包含 `v6` 和 `Worker 自动检测与启动` 相关描述。

### 1.3 Worker 进程检查
```powershell
tasklist /FI "IMAGENAME eq bun.exe" /FO LIST
netstat -ano | findstr 37777
```
确保没有残留的 bun.exe 进程或僵尸端口。

---

## 2. 自动启动测试

### 2.1 启动方式测试
启动 Trae IDE，观察是否自动启动 Worker（无需手动运行 worker-service.cjs）。

### 2.2 无窗口弹出验证
在启动和运行过程中，**不应出现任何 cmd.exe 或 node.exe 黑窗口**。

检查方法：
1. 启动 Trae 后观察任务栏
2. 使用 `tasklist /FI "WINDOWTITLE eq N/A*" /FO LIST` 检查后台进程

### 2.3 日志输出检查
当 MCP Bridge 收到第一个请求时，stderr 应输出：
```
[trae-mem-bridge v6] Auto-started worker via PowerShell (bun=xxx)
[trae-mem-bridge v6] Worker ready after x.xs
```

---

## 3. Web UI 验证

### 3.1 打开 Web UI
```
http://localhost:37777
```

### 3.2 Trae 卡片验证
在 Trae 标签页下，检查卡片显示：

| 检查项 | 预期结果 |
|--------|----------|
| 平台标签 | 显示 "TRAE" 或 "trae" |
| 项目名称 | 正确显示当前项目名 |
| 时间戳 | 格式如 "2026/4/16 03:35:26" |
| 卡片数量 | 应随会话进行而增加 |

### 3.3 数据正确性验证
点击卡片展开，检查：
- `session_id` 是否与 Trae 会话一致
- `platform_source` 是否为 "trae"
- `project` 是否正确提取

---

## 4. 生命周期事件测试

### 4.1 SessionStart 事件
触发条件：打开新会话时
预期行为：
- 自动调用 context hook
- Web UI 显示新会话卡片
- 无控制台错误

### 4.2 UserPromptSubmit 事件
触发条件：发送用户消息时
预期行为：
- 消息被记录
- Web UI 卡片更新
- 内部消息（`<task-notification>`等）被正确过滤

### 4.3 工具执行事件
触发条件：使用 MCP 工具时
预期行为：
- PostToolUse / afterMCPExecution 被调用
- SKIP_TOOLS 列表中的工具被跳过
- 其他工具正常记录

### 4.4 Stop 事件
触发条件：会话停止时
预期行为：
- 自动生成摘要
- 通过 HTTP API 调用 `/api/sessions/summarize`

### 4.5 SessionEnd 事件
触发条件：会话结束时
预期行为：
- 会话被标记为完成
- 通过 HTTP API 调用 `/api/sessions/complete`

---

## 5. 多窗口稳定性测试

### 5.1 测试步骤
1. 打开第一个 Trae 窗口，进行正常对话
2. 打开第二个 Trae 窗口，进行对话
3. 打开第三个 Trae 窗口，测试更多场景

### 5.2 验证项目
- [ ] 每个窗口的会话独立记录
- [ ] Web UI 显示多个 Trae 卡片
- [ ] 不同窗口的数据不混淆
- [ ] 平台标签全部正确显示 "trae"

---

## 6. 数据库验证

### 6.1 查看统计数据
使用 stats 工具：
```
调用 stats 工具
```
预期输出：
```
=== Claude-Mem Statistics ===

Worker Version: x.x.x
Uptime: xxxs
Active Sessions: x

Total Observations: xxx
Total Summaries: xxx
Total Sessions: xxx
Database Size: x.x MB
```

### 6.2 搜索验证
使用 search 工具：
```
调用 search 工具，query="测试"
```
验证搜索结果包含来自 Trae 的记录。

---

## 7. 故障排查

### 7.1 Worker 未启动
**症状**：MCP 请求返回 "ERROR: Worker not available"
**排查**：
1. 检查 bun.exe 是否在 PATH 中
2. 检查 `C:\Users\86150\.bun\bin\bun.exe` 是否存在
3. 查看 stderr 日志输出

### 7.2 端口被占用
**症状**：`netstat` 显示 37777 端口被占用但 worker 无响应
**排查**：
1. `tasklist /FI "IMAGENAME eq bun.exe"` 检查进程
2. `netstat -ano | findstr 37777` 检查端口状态
3. 如果是 TIME_WAIT，尝试等待或重启系统

### 7.3 窗口弹出
**症状**：启动时出现黑窗口
**排查**：
1. 确认使用 PowerShell Base64 编码方式启动
2. 检查 `creationflags=0x08000000` 是否设置
3. 验证 `Start-Process -WindowStyle Hidden` 参数

### 7.4 数据未记录
**症状**：Web UI 没有新卡片
**排查**：
1. 检查 Trae MCP 配置是否正确
2. 查看 MCP Bridge 日志
3. 验证事件类型映射是否正确

---

## 8. 测试结果记录

### 8.1 测试日志模板
```
测试时间: YYYY-MM-DD HH:MM
测试人员: XXX
测试版本: v6.x.x

环境信息:
- Bun 版本: x.x.x
- Node 版本: x.x.x
- 操作系统: Windows 10/11

测试结果:

[ ] 基础环境检查
[ ] 自动启动测试
[ ] Web UI 验证
[ ] 生命周期事件测试
[ ] 多窗口稳定性测试
[ ] 数据库验证

问题记录:
1. ...
2. ...

结论: 通过 / 失败
```

---

## 9. Git 提交规范

每次完成功能修改后，执行 Git 提交：

```bash
git add -A
git commit -m "描述本次修改内容"
git push
```

### 提交信息模板
```
[版本] 描述修改内容

详细说明:
- 修改点1
- 修改点2

测试情况:
- 已通过基础测试
- 已通过 Web UI 验证
```

---

## 10. 快速回归测试

每次代码修改后，运行以下快速测试：

1. 重启 Trae IDE
2. 发送一条测试消息
3. 检查 Web UI 是否出现新卡片
4. 确认无黑窗口弹出
5. 检查控制台无错误输出

如果以上全部通过，则代码修改有效。
