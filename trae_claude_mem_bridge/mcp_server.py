"""
Trae-Claude-Mem Bridge MCP Server v6
将 Trae IDE 的会话事件桥接到 Claude-Mem Worker

基于 worker-service.cjs 源码深度审查后的全面改进:

v5 修复:
A. summarize hook需要transcriptPath但Trae没有 → 直接调用HTTP API /api/sessions/summarize
B. SKIP_TOOLS客户端过滤(减少无谓HTTP请求, 与服务端默认值一致)
C. observation缺少cwd会抛异常 → 防御性默认值
D. session-init空prompt被替换为[media prompt] → 提供有意义的默认值
E. raw normalizer的field mapping → 确保驼峰+下划线双兼容
F. platform=trae让Rt()返回原值 → Web UI显示TRAE标签
G. 内部系统消息过滤 → <task-notification>等XML不当用户prompt
H. session-complete通过HTTP API调用(更可靠)

v6 新增:
I. Worker 自动检测与启动 → 用户无需手动启动Worker, 打开Trae即用 (对标Claude CLI体验)
"""

import json
import sys
import os
import time
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import logging
from pathlib import Path
from typing import Any, Dict, Optional

WORKER_HOST = "127.0.0.1"
WORKER_PORT = 37777
WORKER_URL = f"http://{WORKER_HOST}:{WORKER_PORT}"

PLUGIN_ROOT = r"C:\Users\86150\.claude\plugins\cache\thedotmack\claude-mem\12.1.0"
BUN_RUNNER = os.path.join(PLUGIN_ROOT, "scripts", "bun-runner.js")
WORKER_SERVICE = os.path.join(PLUGIN_ROOT, "scripts", "worker-service.cjs")

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
LOG_FILE = os.path.join(LOG_DIR, "trae_bridge.log")


def setup_logger(name: str = "trae-bridge", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


logger = setup_logger("trae-bridge", logging.INFO)

SKIP_TOOLS = frozenset([
    "ListMcpResourcesTool",
    "SlashCommand",
    "Skill",
    "TodoWrite",
    "AskUserQuestion",
    "trae_mem_hook_event",
    "search",
    "timeline",
    "get_observations",
    "inject",
    "stats",
])


def _make_request(
    endpoint: str,
    method: str = "GET",
    body: Optional[Dict] = None,
    timeout: int = 10
) -> Dict[str, Any]:
    url = f"{WORKER_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    data = None
    if body:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8") if e.fp else str(e)
        except:
            pass
        return {"error": f"HTTP {e.code}", "detail": error_body}
    except Exception as e:
        return {"error": str(e)}


def _is_internal_message(text: str) -> bool:
    if not text:
        return False
    text_stripped = text.strip()
    internal_patterns = [
        "<task-notification>",
        "<task-id>",
        "<tool-use-id>",
        "<output-file>",
        "<status>completed</status>",
        "</task-notification>",
    ]
    for pattern in internal_patterns:
        if pattern in text_stripped:
            return True
    if text_stripped.startswith("<") and ">" in text_stripped[:20]:
        return True
    return False


_worker_process = None


def _find_bun_executable() -> Optional[str]:
    import shutil
    bun_path = shutil.which("bun")
    if bun_path:
        return bun_path
    common_paths = [
        os.path.expanduser(r"~\.bun\bin\bun.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Bun", "bun.exe"),
        r"C:\Users\86150\.bun\bin\bun.exe",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    return None


def _is_worker_running() -> bool:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            result = s.connect_ex((WORKER_HOST, WORKER_PORT))
            return result == 0
    except Exception:
        return False


def _start_worker() -> bool:
    global _worker_process
    bun_exe = _find_bun_executable()
    if not bun_exe:
        logger.error("Bun executable not found, cannot auto-start worker")
        return False
    try:
        import base64
        ps_command = f"Start-Process -FilePath '{bun_exe}' -ArgumentList @('{WORKER_SERVICE}','--daemon') -WindowStyle Hidden"
        ps_encoded = base64.b64encode(ps_command.encode('utf-16le')).decode('ascii')
        subprocess.Popen(
            ["powershell", "-NoProfile", "-EncodedCommand", ps_encoded],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        logger.info(f"Auto-started worker via PowerShell (bun={bun_exe})")
        return True
    except Exception as e:
        logger.error(f"Failed to start worker: {e}")
        return False


def _ensure_worker_running(max_retries: int = 3, retry_interval: float = 2.0) -> bool:
    if _is_worker_running():
        return True
    logger.info("Worker not running, attempting auto-start...")
    if not _start_worker():
        return False
    for attempt in range(max_retries):
        time.sleep(retry_interval)
        if _is_worker_running():
            logger.info(f"Worker ready after {retry_interval * (attempt + 1):.1f}s")
            return True
    logger.warning(f"Worker did not start within {max_retries * retry_interval:.0f}s")
    return False


def _call_worker_hook(hook_type: str, payload: Dict) -> Dict:
    cmd = ["node", BUN_RUNNER, WORKER_SERVICE, "hook", "trae", hook_type]
    stdin_input = json.dumps(payload or {}, ensure_ascii=False)
    try:
        result = subprocess.run(
            cmd,
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PLUGIN_ROOT
        )
        output = result.stdout.strip()
        if output:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {"raw_output": output, "returncode": result.returncode}
        return {"raw_output": output or "(empty)", "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Worker hook timeout after 30s"}
    except FileNotFoundError as e:
        return {"error": f"Executable not found: {e}"}
    except Exception as e:
        return {"error": str(e)}


def _tool_result(text: str, is_error: bool = False) -> Dict:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error
    }


def handle_hook_event(args: Dict) -> Dict:
    if not _ensure_worker_running():
        logger.error("Worker not available (auto-start failed)")
        return {"type": "text", "text": "ERROR: Worker not available (auto-start failed)"}
    event = args.get("event", "")
    payload = args.get("payload", {})
    session_id = payload.get("session_id", "")
    cwd = payload.get("cwd", "") or os.getcwd()

    if not session_id:
        logger.error("Missing session_id in payload")
        return _tool_result("Error: missing session_id", is_error=True)

    project = cwd.replace("\\", "/").rstrip("/").split("/")[-1] if cwd else "unknown"
    logger.debug(f"Handling event: {event} | session: {session_id} | project: {project}")

    hook_mapping = {
        "SessionStart": "context",
        "UserPromptSubmit": "session-init",
        "PostToolUse": "observation",
        "afterMCPExecution": "observation",
        "afterShellExecution": "observation",
        "afterFileEdit": "observation",
        "PreToolUse": "file-context",
        "Stop": "summarize",
        "SessionEnd": "session-complete",
    }

    hook_type = hook_mapping.get(event)
    if not hook_type:
        logger.warning(f"Unknown event type: {event}")
        return _tool_result(f"Unknown event type: {event}", is_error=True)

    # --- 内部消息过滤 ---
    if event == "UserPromptSubmit":
        prompt_text = payload.get("prompt", "")
        if _is_internal_message(prompt_text):
            logger.debug(f"Skipped internal message: {prompt_text[:50]}...")
            return _tool_result(f"[{event}] Skipped internal message", is_error=False)
        if not prompt_text or not prompt_text.strip():
            logger.debug("Skipped empty prompt")
            return _tool_result(f"[{event}] Skipped empty prompt", is_error=False)

    # --- SKIP_TOOLS 客户端过滤 ---
    if event in ("PostToolUse", "afterMCPExecution", "afterShellExecution", "afterFileEdit"):
        tool_name = payload.get("tool_name", "")
        if tool_name in SKIP_TOOLS:
            logger.debug(f"Skipped tool (SKIP_TOOLS): {tool_name}")
            return _tool_result(f"[{event}] Skipped tool: {tool_name}", is_error=False)

    # --- 构造 worker payload (raw normalizer兼容格式) ---
    worker_payload = {
        "sessionId": session_id,
        "session_id": session_id,
        "cwd": cwd,
    }

    # --- 事件特定字段 ---
    if event == "SessionStart":
        worker_payload["source"] = "startup"
        prompt = payload.get("prompt", "")
        if prompt and not _is_internal_message(prompt):
            worker_payload["prompt"] = prompt

    elif event == "UserPromptSubmit":
        worker_payload["prompt"] = payload.get("prompt", "")

    elif event in ("PostToolUse", "afterMCPExecution", "afterShellExecution", "afterFileEdit"):
        tool_name = payload.get("tool_name", "")
        tool_input = payload.get("tool_input", {})
        tool_response = payload.get("tool_response", "")
        worker_payload["toolName"] = tool_name
        worker_payload["tool_name"] = tool_name
        worker_payload["toolInput"] = tool_input
        worker_payload["tool_input"] = tool_input
        if isinstance(tool_response, str) and len(tool_response) > 500:
            tool_response = tool_response[:500] + "...[truncated]"
        worker_payload["toolResponse"] = tool_response
        worker_payload["tool_response"] = tool_response

    elif event == "Stop":
        last_message = payload.get("last_assistant_message", "")
        if last_message:
            worker_payload["last_assistant_message"] = last_message

    # --- 调用方式选择 ---
    # summarize 和 session-complete 通过 HTTP API 更可靠
    # (summarize需要transcriptPath但Trae没有, session-complete不需要hook)
    if event == "Stop":
        return _handle_summarize(session_id, project, cwd, payload)
    elif event == "SessionEnd":
        return _handle_session_complete(session_id, project, cwd)

    # 其他事件通过 worker hook
    result = _call_worker_hook(hook_type, worker_payload)

    if "error" in result:
        logger.error(f"Hook error ({event}/{hook_type}): {result['error']}")
        return _tool_result(f"Hook error ({event}/{hook_type}): {result['error']}", is_error=True)

    # --- 格式化响应 ---
    if event == "SessionStart":
        context_text = ""
        if isinstance(result, dict):
            if "hookSpecificOutput" in result and isinstance(result["hookSpecificOutput"], dict):
                context_text = result["hookSpecificOutput"].get("additionalContext", "")
            elif "additionalContext" in result:
                context_text = result["additionalContext"]
        return _tool_result(
            f"[{event}] Session initialized for '{project}'\n"
            f"Hook type: {hook_type}\n"
            f"{'Context injected (' + str(len(context_text)) + ' chars)' if context_text else 'No context'}"
        )

    elif event == "UserPromptSubmit":
        return _tool_result(f"[{event}] Prompt recorded via {hook_type}")

    elif event in ("PostToolUse", "afterMCPExecution", "afterShellExecution", "afterFileEdit"):
        tool_name = payload.get("tool_name", "?")
        return _tool_result(f"[{event}] Tool captured: {tool_name} via {hook_type}")

    else:
        return _tool_result(f"[{event}] Processed via {hook_type}")


def _handle_summarize(session_id: str, project: str, cwd: str, payload: Dict) -> Dict:
    """
    summarize hook需要transcriptPath来提取最后一条assistant消息,
    但Trae没有transcript文件。替代方案: 直接通过HTTP API调用摘要生成。
    """
    last_message = payload.get("last_assistant_message", "")
    if not last_message:
        last_message = payload.get("summary_text", "")

    if not last_message:
        result = _call_worker_hook("summarize", {
            "sessionId": session_id,
            "session_id": session_id,
            "cwd": cwd,
        })
        if "error" in result:
            return _tool_result(f"[Stop] Summarize via hook: {result['error']}", is_error=True)
        return _tool_result(f"[Stop] Summary triggered via hook for '{project}'")

    api_result = _make_request("/api/sessions/summarize", method="POST", body={
        "contentSessionId": session_id,
        "last_assistant_message": last_message,
    }, timeout=30)

    if "error" in api_result:
        result = _call_worker_hook("summarize", {
            "sessionId": session_id,
            "session_id": session_id,
            "cwd": cwd,
        })
        return _tool_result(f"[Stop] Summary fallback to hook for '{project}'")

    return _tool_result(f"[Stop] Summary generated via API for '{project}'")


def _handle_session_complete(session_id: str, project: str, cwd: str) -> Dict:
    """
    session-complete: 直接通过HTTP API标记会话完成(更可靠)
    """
    api_result = _make_request("/api/sessions/complete", method="POST", body={
        "contentSessionId": session_id,
        "platformSource": "trae",
    }, timeout=10)

    if "error" not in api_result:
        return _tool_result(f"[SessionEnd] Session completed for '{project}'")

    result = _call_worker_hook("session-complete", {
        "sessionId": session_id,
        "session_id": session_id,
        "cwd": cwd,
    })
    if "error" in result:
        return _tool_result(f"[SessionEnd] Fallback hook error: {result['error']}", is_error=True)
    return _tool_result(f"[SessionEnd] Session completed via hook for '{project}'")


def handle_search(args: Dict) -> Dict:
    if not _ensure_worker_running():
        return {"type": "text", "text": "ERROR: Worker not available (auto-start failed)"}
    query = args.get("query", "")
    limit = args.get("limit", 20)
    project = args.get("project", "")
    params = f"?limit={limit}"
    if query:
        params += f"&q={urllib.parse.quote(query)}"
    if project:
        params += f"&project={urllib.parse.quote(project)}"
    result = _make_request(f"/api/observations{params}")
    if "error" in result:
        return _tool_result(f"Search error: {result['error']}", is_error=True)
    observations = result.get("observations", [])
    total = len(observations)
    output = f"Found {total} results for '{query}':\n\n"
    for obs in observations[:10]:
        output += f"- [{obs.get('id', '?')}] {obs.get('type', '?')} | project:{obs.get('project', '?')} | platform:{obs.get('platform_source', '?')}\n"
        text = obs.get('text') or ''
        output += f"  {str(text)[:150]}\n\n"
    return _tool_result(output)


def handle_timeline(args: Dict) -> Dict:
    if not _ensure_worker_running():
        return {"type": "text", "text": "ERROR: Worker not available (auto-start failed)"}
    try:
        observation_id = args.get("observation_id")
        query = args.get("query", "")
        if observation_id:
            result = _make_request(f"/api/timeline/{observation_id}")
        elif query:
            result = _make_request(f"/api/timeline?q={urllib.parse.quote(query)}")
        else:
            return _tool_result("Error: need observation_id or query", is_error=True)
        if "error" in result:
            return _tool_result(f"Timeline error: {result['error']}", is_error=True)
        items = result.get("items", []) if isinstance(result, dict) else []
        output = f"Timeline ({len(items)} items):\n\n"
        for item in items[:10]:
            output += f"- [{item.get('id', '?')}] {item.get('title', '')}\n"
            output += f"  {item.get('created_at', '')} | {item.get('type', '')}\n\n"
        return _tool_result(output)
    except Exception as e:
        return _tool_result(f"Timeline error: {e}", is_error=True)


def handle_get_observations(args: Dict) -> Dict:
    if not _ensure_worker_running():
        return {"type": "text", "text": "ERROR: Worker not available (auto-start failed)"}
    try:
        ids = args.get("ids", [])
        if isinstance(ids, int):
            ids = [ids]
        elif isinstance(ids, str):
            ids = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
        if not ids:
            return _tool_result("Error: no valid IDs provided", is_error=True)
        result = _make_request("/api/observations/batch", method="POST", body={"ids": ids})
        if "error" in result:
            return _tool_result(f"Error: {result['error']}", is_error=True)
        observations = result if isinstance(result, list) else []
        output = f"Fetched {len(observations)} observations:\n\n"
        for obs in observations:
            output += f"=== #{obs.get('id', '?')} ===\n"
            output += f"Type: {obs.get('type', '')}\n"
            output += f"Project: {obs.get('project', '')}\n"
            text = obs.get('text') or 'N/A'
            output += f"Text:\n{text}\n\n"
        return _tool_result(output)
    except Exception as e:
        return _tool_result(f"Get observations error: {e}", is_error=True)


def handle_inject(args: Dict) -> Dict:
    if not _ensure_worker_running():
        return {"type": "text", "text": "ERROR: Worker not available (auto-start failed)"}
    try:
        project = args.get("project", "")
        limit = args.get("limit", 50)
        params = f"?limit={limit}"
        if project:
            params += f"&project={urllib.parse.quote(project)}"
        result = _make_request(f"/api/context/inject{params}")
        if "error" in result:
            return _tool_result(f"Inject error: {result['error']}", is_error=True)
        context = result.get("context") if isinstance(result, dict) else str(result)
        return _tool_result(context)
    except Exception as e:
        return _tool_result(f"Inject error: {e}", is_error=True)


def handle_stats(args: Dict) -> Dict:
    if not _ensure_worker_running():
        return {"type": "text", "text": "ERROR: Worker not available (auto-start failed)"}
    try:
        result = _make_request("/api/stats")
        if "error" in result:
            return _tool_result(f"Stats error: {result['error']}", is_error=True)
        db_info = result.get("database", {})
        worker_info = result.get("worker", {})
        output = "=== Claude-Mem Statistics ===\n\n"
        output += f"Worker Version: {worker_info.get('version', 'N/A')}\n"
        output += f"Uptime: {worker_info.get('uptime', 0)}s\n"
        output += f"Active Sessions: {worker_info.get('activeSessions', 0)}\n\n"
        output += f"Total Observations: {db_info.get('observations', 0)}\n"
        output += f"Total Summaries: {db_info.get('summaries', 0)}\n"
        output += f"Total Sessions: {db_info.get('sessions', 0)}\n"
        size_bytes = db_info.get('size', 0)
        if size_bytes:
            output += f"Database Size: {size_bytes / 1024 / 1024:.1f} MB\n"
        return _tool_result(output)
    except Exception as e:
        return _tool_result(f"Stats error: {e}", is_error=True)


TOOLS = [
    {
        "name": "trae_mem_hook_event",
        "description": """接收Trae IDE的生命周期事件并转发到Claude-Mem Worker (v6 - 自动启动Worker)。

支持事件类型:
- SessionStart: 会话开始(初始化+注入历史上下文) -> hook: context
- UserPromptSubmit: 用户输入prompt -> hook: session-init (过滤内部消息+空prompt)
- PostToolUse/afterMCPExecution/afterShellExecution/afterFileEdit: 工具执行后 -> hook: observation (SKIP_TOOLS过滤)
- Stop: 停止时(生成会话摘要) -> HTTP API /api/sessions/summarize
- SessionEnd: 会话结束 -> HTTP API /api/sessions/complete

v6特性: Worker自动检测与启动(用户无需手动启动, 打开Trae即用)
v5改进: SKIP_TOOLS客户端过滤, summarize/session-complete走HTTP API, 驼峰+下划线双兼容, 防御性默认值""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event": {
                    "type": "string",
                    "description": "事件类型: SessionStart, UserPromptSubmit, PostToolUse, Stop, SessionEnd等"
                },
                "payload": {
                    "type": "object",
                    "description": "事件payload，包含session_id, cwd, tool_name, tool_input, tool_response, last_assistant_message等字段"
                }
            },
            "required": ["event", "payload"]
        }
    },
    {
        "name": "search",
        "description": "搜索Claude-Mem中的观察记录，支持全文搜索和过滤",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "number", "description": "返回数量限制"},
                "project": {"type": "string", "description": "项目名过滤"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "timeline",
        "description": "获取特定观察或查询的时间线上下文",
        "inputSchema": {
            "type": "object",
            "properties": {
                "observation_id": {"type": "number", "description": "观察ID"},
                "query": {"type": "string", "description": "搜索查询"}
            }
        }
    },
    {
        "name": "get_observations",
        "description": "按ID批量获取观察记录的完整详情",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "number"}},
                        {"type": "string"}
                    ],
                    "description": "观察ID列表或逗号分隔字符串"
                }
            },
            "required": ["ids"]
        }
    },
    {
        "name": "inject",
        "description": "获取可注入到新会话的历史上下文块",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "项目名"},
                "limit": {"type": "number", "description": "观察数量限制"}
            }
        }
    },
    {
        "name": "stats",
        "description": "获取Claude-Mem数据库统计信息",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

TOOL_HANDLERS = {
    "trae_mem_hook_event": handle_hook_event,
    "search": handle_search,
    "timeline": handle_timeline,
    "get_observations": handle_get_observations,
    "inject": handle_inject,
    "stats": handle_stats
}


def _write(obj: Any):
    line = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _read() -> Optional[Dict]:
    try:
        line = input()
        return json.loads(line)
    except EOFError:
        return None


def serve_stdio():
    _write({"jsonrpc": "2.0", "result": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "serverInfo": {"name": "trae-mem-bridge", "version": "6.0.0"}
    }})
    _ensure_worker_running()
    while True:
        raw = _read()
        if not raw:
            break
        req_id = raw.get("id")
        method = raw.get("method", "")
        params = raw.get("params", {})
        if method == "initialize":
            _write({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "trae-mem-bridge", "version": "6.0.0"}
                }
            })
        elif method == "tools/list":
            _write({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS}
            })
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            handler = TOOL_HANDLERS.get(name)
            if handler:
                result = handler(args)
            else:
                result = _tool_result(f"Unknown tool: {name}", is_error=True)
            _write({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result
            })


if __name__ == "__main__":
    logger.info("Starting MCP server...")
    logger.info(f"Plugin root: {PLUGIN_ROOT}")
    logger.info(f"Bun runner: {BUN_RUNNER}")
    logger.info(f"Auto-start enabled | platform=trae | SKIP_TOOLS={len(SKIP_TOOLS)} tools | HTTP API for summarize/complete")
    serve_stdio()
