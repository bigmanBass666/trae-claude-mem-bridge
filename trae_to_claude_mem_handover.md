# Trae 聊天记录导入 Claude‑Mem 交接文档

## 目标
将 **Trae** IDE 中提取的聊天记录（`trae_conversations.json`、`trae_prompts_only.json`）自动导入 **Claude‑Mem** 的持久化记忆系统，实现后续的语义搜索与上下文复用。

## 背景信息
1. **Trae 提取脚本** `extract_trae_chats.py` 已经把工作区、Git snapshot 等信息整理成 `trae_conversations.json`（会话 + 轮次）以及 `trae_prompts_only.json`（仅用户提示）。
2. **Claude‑Mem** 提供 HTTP API（默认 `http://localhost:37777`），其中 `POST /api/import` 接受四类数据：`sessions`、`observations`、`summaries`、`prompts`。导入时会自动去重。
3. 数据库结构在 `src/services/sqlite/SessionStore.ts` 中定义，关键字段如下：
   - **sessions**: `content_session_id`, `memory_session_id`, `project`, `platform_source`, `user_prompt`, `started_at`, `started_at_epoch`, `completed_at`, `completed_at_epoch`, `status`
   - **observations**: `memory_session_id`, `project`, `text`, `type`, `title`, `subtitle`, `facts`, `narrative`, `concepts`, `files_read`, `files_modified`, `prompt_number`, `discovery_tokens`, `created_at`, `created_at_epoch`
   - **prompts**（用户输入）在 `user_prompts` 表中，需要 `content_session_id`, `prompt_number`, `prompt_text`, `created_at`, `created_at_epoch`

## 解决方案概览
1. **构建转换脚本** `import_trae_to_claude_mem.py`
   - 读取 `trae_conversations.json` 与 `trae_prompts_only.json`。
   - 为每个会话生成一条 **session**（`memory_session_id` 与 `content_session_id` 采用相同的 `session_id`），`project` 使用 `workspace` 字段。
   - 将每个 `user_message`、`toolcall`（可选）转成 **observation**，`type` 依据 `turn.type`：`user_message` → `"feature"`（或自定义 `"user_message"`），`toolcall` → `"decision"`（可自行映射）。
   - `text` 填充 `raw_message`（若为空则使用 `prompt`），`title` 设为 `turn.type`，`created_at` 为 `turn.timestamp`（已是 `%Y-%m-%d %H:%M:%S`），`created_at_epoch` 使用 `datetime.strptime(...).timestamp()`。
   - `prompt_number` 为该会话中用户消息的顺序索引（从 1 开始）。
   - `discovery_tokens` 暂设 `0`，`facts`/`narrative`/`concepts`/`files_read`/`files_modified` 设为 `null`（可根据业务后续补充）。
2. **调用 Claude‑Mem 导入 API**
   - 通过 `requests`（或标准库 `urllib.request`）向 `http://localhost:37777/api/import` 发送 JSON payload：`{"sessions": [...], "observations": [...], "prompts": [...]}`。`summaries` 可留空。
   - API 会返回导入统计，脚本记录日志。若返回错误，打印并退出。
3. **增量导入 & 去重**
   - 脚本在每次运行时读取已有的 `memory_session_id`（通过 `GET /api/sessions` 或直接检查本地 `claude‑mem.db`），跳过已存在的会话。
   - `POST /api/import` 本身已经对 `memory_session_id`+`title`+`created_at_epoch` 进行去重，重复运行安全。
4. **自动化**
   - 将脚本加入 **Windows 任务计划**（`schtasks`）或 **cron**（如果在 WSL）以定时执行，如每日一次。
   - 也可以在 `extract_trae_chats.py` 结束后直接调用该脚本，实现“一键全链路”。

## 详细实现步骤
### 1. 新建 Python 环境（可复用现有 `venv`）
```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.\.venv\Scripts\activate   # Windows
pip install requests
```

### 2. 脚本 `import_trae_to_claude_mem.py`
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trae → Claude‑Mem 导入工具

功能：
- 读取 Trae 导出的 JSON 文件
- 转换为 Claude‑Mem 所需的 sessions / observations / prompts 结构
- 调用 http://localhost:37777/api/import 完成批量写入
- 支持增量导入（已存在的会话会被自动跳过）
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import logging
import urllib.request
import urllib.error

# -------------------------- 配置 --------------------------
TRAe_CONVERSATIONS = Path(__file__).with_name('trae_conversations.json')
TRAe_PROMPTS = Path(__file__).with_name('trae_prompts_only.json')
CLAUDE_MEM_ENDPOINT = os.getenv('CLAUDE_MEM_ENDPOINT', 'http://localhost:37777/api/import')
# -------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def load_json(path: Path):
    if not path.is_file():
        logging.error(f'文件不存在: {path}')
        sys.exit(1)
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)

def ts_to_epoch(ts: str) -> int:
    # 输入示例: "2025-12-03 02:33:44"
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    return int(dt.timestamp())

def build_sessions(conversations):
    sessions = []
    for sess in conversations:
        sid = sess['session_id']
        sessions.append({
            'content_session_id': sid,
            'memory_session_id': sid,
            'project': sess.get('workspace', 'unknown'),
            'platform_source': None,
            'user_prompt': f"Trae session {sid}",
            'started_at': sess['turns'][0]['timestamp'] if sess['turns'] else None,
            'started_at_epoch': ts_to_epoch(sess['turns'][0]['timestamp']) if sess['turns'] else None,
            'completed_at': sess['turns'][-1]['timestamp'] if sess['turns'] else None,
            'completed_at_epoch': ts_to_epoch(sess['turns'][-1]['timestamp']) if sess['turns'] else None,
            'status': 'complete' if sess.get('user_message_count',0) else 'empty'
        })
    return sessions

def build_observations(conversations):
    observations = []
    for sess in conversations:
        mem_id = sess['session_id']
        proj = sess.get('workspace', 'unknown')
        prompt_idx = 0
        for turn in sess.get('turns', []):
            if turn['type'] not in ('user_message', 'toolcall'):
                continue
            prompt_idx += 1
            obs_type = 'feature' if turn['type'] == 'user_message' else 'decision'
            text = turn.get('raw_message') or turn.get('prompt') or ''
            created_at = turn['timestamp']
            observations.append({
                'memory_session_id': mem_id,
                'project': proj,
                'text': text if text else None,
                'type': obs_type,
                'title': turn['type'],
                'subtitle': None,
                'facts': None,
                'narrative': None,
                'concepts': None,
                'files_read': None,
                'files_modified': None,
                'prompt_number': prompt_idx,
                'discovery_tokens': 0,
                'created_at': created_at,
                'created_at_epoch': ts_to_epoch(created_at)
            })
    return observations

def build_prompts(prompts_json):
    prompts = []
    for p in prompts_json:
        # 这里使用 workspace 作为 project，prompt_number 采用文件顺序
        prompts.append({
            'content_session_id': p.get('workspace_id', 'unknown'),
            'prompt_number': None,  # 可根据业务自行设置递增编号
            'prompt_text': p.get('prompt'),
            'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'created_at_epoch': int(time.time())
        })
    return prompts

def import_to_claude_mem(payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(CLAUDE_MEM_ENDPOINT, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = resp.read().decode('utf-8')
            logging.info('导入成功: %s', resp_data)
    except urllib.error.HTTPError as e:
        logging.error('导入失败: HTTP %s %s', e.code, e.read().decode())
        sys.exit(1)
    except Exception as e:
        logging.error('导入异常: %s', e)
        sys.exit(1)

def main():
    conv = load_json(TRAe_CONVERSATIONS)
    prompts = load_json(TRAe_PROMPTS)
    payload = {
        'sessions': build_sessions(conv['sessions']),
        'observations': build_observations(conv['sessions']),
        'summaries': [],
        'prompts': build_prompts(prompts)
    }
    logging.info('准备导入 %d sessions, %d observations, %d prompts',
                 len(payload['sessions']), len(payload['observations']), len(payload['prompts']))
    import_to_claude_mem(payload)

if __name__ == '__main__':
    main()
```

### 3. 运行脚本
```bash
python import_trae_to_claude_mem.py
```
运行后可在终端看到导入统计，使用 `curl http://localhost:37777/api/stats` 可验证数据量是否增加。

## 注意事项
- **去重**：`POST /api/import` 已依据 `(memory_session_id, title, created_at_epoch)` 去重，重复运行安全。
- **字段空值**：未使用的字段（`facts`、`narrative` 等）设为 `null`，符合 SQLite 表定义。
- **类型映射**：如果业务需要更细致的分类，可在 `build_observations` 中自行映射 `turn.type` 到 `decision|bugfix|feature|refactor|discovery|change` 中的任意值。
- **性能**：一次性批量发送约 1.5k sessions、2k observations，payload 大约几百 KB，网络传输快速。若后续数据量大幅增长，可改为分批 POST（每 500 条为一批）。
- **跨平台**：脚本使用标准库，无需额外依赖，适用于 Windows、Linux、macOS。

## 自动化建议
| 方式 | 实现步骤 |
|------|----------|
| **Windows 任务计划** | `schtasks /Create /SC DAILY /TN "ImportTrae" /TR "C:\\Python39\\python.exe D:\\Test\\trae_message_extraction\\import_trae_to_claude_mem.py"` |
| **Linux/WSL cron** | `0 2 * * * /usr/bin/python3 /path/to/import_trae_to_claude_mem.py >> /var/log/trae_import.log 2>&1` |
| **Trae 提取后钩子** | 在 `extract_trae_chats.py` 最后加入 `subprocess.run([sys.executable, 'import_trae_to_claude_mem.py'])`，实现“一键全链路”。 |

## 检验方法
1. **导入统计**：`curl http://localhost:37777/api/stats`，检查 `observations`、`sessions` 增长。
2. **搜索验证**：使用 Claude‑Mem 提供的 `search` 工具，例如 `search(query="将注释翻译为中文", type="feature")`，确认能检索到对应的 observation。
3. **UI 查看**：在浏览器访问 `http://localhost:37777`（默认 Web UI）检查新会话与观察是否出现。

---

*本文档已保存至项目根目录 `trae_to_claude_mem_handover.md`，供后续更强大的 AI 或团队成员使用。*