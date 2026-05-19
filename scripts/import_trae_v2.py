#!/usr/bin/env python3
"""
Trae 聊天记录导入 claude-mem v2
基于解密的 database.db 数据，直接写入 SQLite

数据源: trae_full_data.json (223 对话, 31K 消息)
目标: ~/.claude-mem/claude-mem.db
"""

import sqlite3
import json
import os
import re
import hashlib
import uuid
from datetime import datetime, timezone
from collections import Counter
from urllib.parse import unquote

# 配置
DATA_SOURCE = r"D:\Test\claude_test\subagent_test\trae_db_export\trae_full_data.json"
CLAUDE_MEM_DB = os.path.expanduser(r"~\.claude-mem\claude-mem.db")
PROJECT_MAP_FILE = os.path.join(os.path.dirname(__file__), "trae_project_map.json")
PROJECT_PATHS_FILE = os.path.join(os.path.dirname(__file__), "trae_project_paths.json")

# 自动生成的标题（过滤掉）
AUTO_TITLES = {
    "开始", "Review Code Changes", "Read Code Review Diffs",
    "分析重构问题", "你好", "Untitled", "",
}

# Observation 类型关键词
TYPE_KEYWORDS = {
    "bugfix": ["修复", "fix", "bug", "error", "解决", "问题", "错误", "异常", "crash"],
    "feature": ["创建", "新增", "实现", "create", "implement", "添加", "开发", "构建"],
    "refactor": ["重构", "优化", "refactor", "改进", "整理", "clean"],
    "decision": ["选择", "决定", "方案", "架构", "architecture", "decision", "采用"],
    "discovery": ["发现", "了解", "学习", "原来", "learn", "研究", "调研", "探索"],
}


def content_hash(memory_session_id, title, narrative):
    """计算 content_hash"""
    raw = f"{memory_session_id or ''}\x00{title or ''}\x00{narrative or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def extract_user_input(content):
    """从 user 消息中提取真实输入"""
    # 尝试提取 <user_input> 标签
    match = re.search(r"<user_input>\s*(.*?)\s*</user_input>", content, re.DOTALL)
    if match:
        text = match.group(1).strip()
        if text:
            return text

    # 尝试提取 <command> 标签
    match = re.search(r"<command>\s*(.*?)\s*</command>", content, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 如果没有标签，检查是否是纯文本（非 system-reminder）
    if "<system-reminder>" not in content and len(content.strip()) > 3:
        return content.strip()

    return None


def extract_file_paths(text):
    """从文本中提取文件路径"""
    paths = re.findall(r"[A-Za-z]:\\[^\s`\"<>]+", text)
    return [p.replace("\\", "/") for p in paths]


def infer_project_from_paths(paths):
    """从文件路径推断项目名"""
    skip = {
        "users", "appdata", "roaming", "trae cn", "user", "workspacestorage",
        "test", "working", "code", "documents", "desktop", "programming_projects",
        "downloads", "apps", ".claude", ".trae", "src", "components", "scripts",
        "docs", "config", "public", "dist", "build", "node_modules", ".git",
    }
    names = []
    for path in paths:
        parts = path.split("/")
        # 找 programming_projects 下的项目
        for i, part in enumerate(parts):
            if part.lower() == "programming_projects" and i + 1 < len(parts):
                names.append(parts[i + 1])
        # 找 Test 下的项目
        for i, part in enumerate(parts):
            if part.lower() == "test" and i + 1 < len(parts):
                names.append(parts[i + 1])
        # 找 Working 下的项目
        for i, part in enumerate(parts):
            if part.lower() == "working" and i + 2 < len(parts) and parts[i + 1].lower() == "programming_projects":
                names.append(parts[i + 2])
    return names


def infer_project_name(project_id, conversations, manual_map=None, project_paths=None):
    """推断项目名"""
    # 0. 手动映射优先
    if manual_map and project_id in manual_map:
        return manual_map[project_id]

    # 1. 从 database.db 的 project + multi_root_path 表获取真实路径
    if project_paths and project_id in project_paths:
        real_path = project_paths[project_id]
        name = path_to_project_name(real_path)
        if name:
            return name

    # 2. 从消息中的文件路径推断
    all_paths = []
    for conv in conversations:
        for msg in conv.get("messages", []):
            if msg.get("role") == "user":
                all_paths.extend(extract_file_paths(msg.get("content", "")))
    path_names = infer_project_from_paths(all_paths)
    if path_names:
        counter = Counter(path_names)
        return counter.most_common(1)[0][0]

    # 3. 从有意义的 session_title 推断
    titles = []
    for conv in conversations:
        title = conv.get("session", {}).get("session_title", "")
        if title and title not in AUTO_TITLES and len(title) > 2:
            titles.append(title)
    if titles:
        counter = Counter(titles)
        return counter.most_common(1)[0][0]

    # 4. fallback
    return f"project-{project_id[-8:]}"


def infer_observation_type(user_msg, assistant_reply):
    """推断 observation 类型"""
    combined = (user_msg + " " + assistant_reply).lower()
    scores = {}
    for obs_type, keywords in TYPE_KEYWORDS.items():
        scores[obs_type] = sum(1 for kw in keywords if kw in combined)

    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    return "change"


def summarize_assistant_reply(reply, max_len=200):
    """生成 assistant 回复的摘要"""
    if not reply:
        return ""
    # 取第一段非空文本
    lines = reply.split("\n")
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("```"):
            return line[:max_len]
    return reply[:max_len]


def extract_facts(reply, max_facts=5):
    """从 assistant 回复中提取关键事实"""
    if not reply:
        return []
    facts = []
    # 提取列表项
    for line in reply.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("* ") or re.match(r"^\d+\.", line):
            fact = re.sub(r"^[-*\d.]\s*", "", line).strip()
            if len(fact) > 10 and len(facts) < max_facts:
                facts.append(fact)
    # 如果没有列表项，取前几句
    if not facts:
        sentences = re.split(r"[。！？.!?]", reply)
        for s in sentences:
            s = s.strip()
            if len(s) > 15 and len(facts) < max_facts:
                facts.append(s)
    return facts


def load_manual_map():
    """加载手动映射表"""
    if os.path.exists(PROJECT_MAP_FILE):
        with open(PROJECT_MAP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_project_paths():
    """加载项目路径映射（来自 database.db 的 project + multi_root_path 表）"""
    if os.path.exists(PROJECT_PATHS_FILE):
        with open(PROJECT_PATHS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 过滤掉注释字段
            return {k: v for k, v in data.items() if not k.startswith("_")}
    return {}


def path_to_project_name(path):
    """从真实项目路径提取项目名"""
    if not path:
        return None
    # 取最后一个非空目录名
    parts = path.replace("\\", "/").rstrip("/").split("/")
    # 跳过常见根目录
    skip = {"test", "working", "code", "programming_projects", "installations"}
    for part in reversed(parts):
        if part.lower() not in skip and part:
            return part
    return None


def save_manual_map(mapping):
    """保存手动映射表"""
    with open(PROJECT_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Trae 聊天记录导入 claude-mem v2")
    parser.add_argument("--dry-run", action="store_true", help="只分析不导入")
    parser.add_argument("--source", type=str, default=DATA_SOURCE, help="源数据路径")
    parser.add_argument("--db", type=str, default=CLAUDE_MEM_DB, help="目标数据库路径")
    args = parser.parse_args()

    # Phase 0: 预检
    print("=== Phase 0: 预检 ===")
    if not os.path.exists(args.source):
        print(f"错误: 源数据不存在: {args.source}")
        return

    print(f"源数据: {args.source}")
    print(f"目标数据库: {args.db}")

    # Phase 1: 数据加载
    print("\n=== Phase 1: 数据加载与清洗 ===")
    with open(args.source, "r", encoding="utf-8") as f:
        data = json.load(f)

    conversations = data["conversations"]
    print(f"加载 {len(conversations)} 个对话")

    # 加载手动映射
    manual_map = load_manual_map()

    # 加载项目路径映射
    project_paths = load_project_paths()
    print(f"加载 {len(project_paths)} 个项目路径映射")

    # 按 project_id 分组
    project_groups = {}
    for conv in conversations:
        pid = conv.get("session", {}).get("project_id", "unknown")
        if pid not in project_groups:
            project_groups[pid] = []
        project_groups[pid].append(conv)

    print(f"发现 {len(project_groups)} 个项目")

    # 推断项目名
    project_names = {}
    for pid, convs in project_groups.items():
        name = infer_project_name(pid, convs, manual_map, project_paths)
        project_names[pid] = name
        print(f"  {pid[:16]}... -> {name} ({len(convs)} 对话)")

    # Phase 2-4: 处理每个对话
    print("\n=== Phase 2-4: 处理对话 ===")

    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()

    # Phase 0: 清理旧数据
    if not args.dry_run:
        print("清理旧 trae 数据...")
        cursor.execute("DELETE FROM observations WHERE memory_session_id IN (SELECT memory_session_id FROM sdk_sessions WHERE platform_source='trae')")
        deleted_obs = cursor.rowcount
        cursor.execute("DELETE FROM user_prompts WHERE content_session_id IN (SELECT content_session_id FROM sdk_sessions WHERE platform_source='trae')")
        deleted_prompts = cursor.rowcount
        cursor.execute("DELETE FROM sdk_sessions WHERE platform_source='trae'")
        deleted_sessions = cursor.rowcount
        print(f"  删除: {deleted_sessions} sessions, {deleted_obs} observations, {deleted_prompts} user_prompts")

    # 统计
    total_sessions = 0
    total_obs = 0
    total_prompts = 0

    for conv in conversations:
        session = conv.get("session", {})
        messages = conv.get("messages", [])

        session_id = session.get("session_id", "")
        project_id = session.get("project_id", "")
        project_name = project_names.get(project_id, f"project-{project_id[-8:]}")
        session_title = session.get("session_title", "")
        created_at = int(session.get("created_at", 0))
        updated_at = int(session.get("updated_at", 0))

        # 跳过无效对话
        if not session_id or not messages:
            continue

        # 生成 memory_session_id
        memory_sid = str(uuid.uuid4())

        # 时间戳
        dt_start = datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat() if created_at else ""
        dt_end = datetime.fromtimestamp(updated_at, tz=timezone.utc).isoformat() if updated_at else ""

        # 提取首条用户消息作为 user_prompt
        first_user_msg = ""
        for msg in messages:
            if msg.get("role") == "user":
                extracted = extract_user_input(msg.get("content", ""))
                if extracted:
                    first_user_msg = extracted[:500]
                    break

        # Phase 2: 创建 session
        if not args.dry_run:
            cursor.execute("""
                INSERT INTO sdk_sessions (content_session_id, memory_session_id, project,
                    platform_source, user_prompt, started_at, started_at_epoch, completed_at,
                    completed_at_epoch, status)
                VALUES (?, ?, ?, 'trae', ?, ?, ?, ?, ?, 'completed')
            """, (session_id, memory_sid, project_name, first_user_msg,
                  dt_start, created_at * 1000, dt_end, updated_at * 1000))
        total_sessions += 1

        # Phase 3: 生成 observations（按轮次）
        turns = []
        current_turn = {"user": None, "assistant_replies": []}

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            ts = int(msg.get("timestamp", 0))

            if role == "user":
                # 保存上一个轮次
                if current_turn["user"] is not None:
                    turns.append(current_turn)
                current_turn = {"user": content, "user_ts": ts, "assistant_replies": []}
            elif role == "assistant" and content.strip():
                current_turn["assistant_replies"].append(content)

        # 保存最后一个轮次
        if current_turn["user"] is not None:
            turns.append(current_turn)

        # 为每个轮次生成 observation
        for turn in turns:
            user_content = turn.get("user", "")
            user_text = extract_user_input(user_content) or user_content
            assistant_replies = turn.get("assistant_replies", [])
            assistant_text = "\n\n".join(assistant_replies[:3])  # 最多取 3 条回复

            if not user_text or len(user_text.strip()) < 3:
                continue
            if not assistant_text.strip():
                continue

            # 推断类型
            obs_type = infer_observation_type(user_text, assistant_text)

            # 生成 title
            title = user_text[:50].replace("\n", " ").strip()

            # 生成 subtitle
            subtitle = summarize_assistant_reply(assistant_text, 100)

            # 生成 facts
            facts = extract_facts(assistant_text)

            # 生成 narrative
            narrative = f"用户请求: {user_text[:200]}\n\nAI 回复摘要: {subtitle}"

            # 计算 content_hash
            ch = content_hash(memory_sid, title, narrative)

            # 时间戳
            ts = turn.get("user_ts", created_at)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else dt_start

            if not args.dry_run:
                cursor.execute("""
                    INSERT INTO observations (memory_session_id, project, type, title, subtitle,
                        facts, narrative, content_hash, created_at, created_at_epoch)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (memory_sid, project_name, obs_type, title, subtitle,
                      json.dumps(facts, ensure_ascii=False), narrative, ch,
                      dt, ts * 1000 if ts else created_at * 1000))
            total_obs += 1

        # Phase 4: 写入 user_prompts
        prompt_num = 0
        for msg in messages:
            if msg.get("role") == "user":
                extracted = extract_user_input(msg.get("content", ""))
                if extracted and len(extracted.strip()) >= 3:
                    prompt_num += 1
                    ts = int(msg.get("timestamp", 0))
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else dt_start

                    if not args.dry_run:
                        cursor.execute("""
                            INSERT INTO user_prompts (content_session_id, prompt_number,
                                prompt_text, created_at, created_at_epoch)
                            VALUES (?, ?, ?, ?, ?)
                        """, (session_id, prompt_num, extracted[:2000], dt,
                              ts * 1000 if ts else created_at * 1000))
                    total_prompts += 1

    # Phase 5: 验证
    print("\n=== Phase 5: 验证 ===")

    if not args.dry_run:
        # 重建 FTS5
        print("重建 FTS5 索引...")
        cursor.execute("INSERT INTO observations_fts(observations_fts) VALUES('rebuild')")
        cursor.execute("INSERT INTO user_prompts_fts(user_prompts_fts) VALUES('rebuild')")

        conn.commit()

        # 统计验证
        cursor.execute("SELECT COUNT(*) FROM sdk_sessions WHERE platform_source='trae'")
        db_sessions = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM observations WHERE memory_session_id IN (SELECT memory_session_id FROM sdk_sessions WHERE platform_source='trae')")
        db_obs = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM user_prompts WHERE content_session_id IN (SELECT content_session_id FROM sdk_sessions WHERE platform_source='trae')")
        db_prompts = cursor.fetchone()[0]

        print(f"数据库验证:")
        print(f"  Sessions: {db_sessions} (预期 {total_sessions})")
        print(f"  Observations: {db_obs} (预期 {total_obs})")
        print(f"  User Prompts: {db_prompts} (预期 {total_prompts})")

        # 项目名验证
        cursor.execute("SELECT project, COUNT(*) FROM sdk_sessions WHERE platform_source='trae' GROUP BY project ORDER BY COUNT(*) DESC")
        print(f"\n项目分布:")
        for proj, cnt in cursor.fetchall():
            print(f"  {proj}: {cnt} sessions")

        # FTS5 验证
        cursor.execute("SELECT COUNT(*) FROM observations_fts")
        fts_count = cursor.fetchone()[0]
        print(f"\nFTS5 索引: {fts_count} 条 (应等于 {db_obs})")

    conn.close()

    print(f"\n=== 完成 ===")
    print(f"处理: {total_sessions} sessions, {total_obs} observations, {total_prompts} user_prompts")
    if args.dry_run:
        print("(dry-run 模式，未写入数据库)")


if __name__ == "__main__":
    main()
