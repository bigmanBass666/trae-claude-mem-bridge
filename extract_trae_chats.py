#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae CN 聊天记录提取器
从 workspaceStorage + Git snapshot repos 提取完整的对话历史
"""
import os
import sqlite3
import json
import zlib
import datetime

SNAPSHOT_BASE = "C:/Users/{username}/AppData/Roaming/Trae CN/ModularData/ai-agent/snapshot"
WORKSPACE_DIR = "C:/Users/{username}/AppData/Roaming/Trae CN/User/workspaceStorage"
OUTPUT_DIR = "D:/Test/trae_message_extraction"

def read_obj(path):
    return zlib.decompress(open(path, 'rb').read())

def parse_obj(content):
    null_pos = content.index(b'\x00')
    header = content[:null_pos].decode('ascii', errors='replace')
    body = content[null_pos+1:]
    return header.split()[0], body

def get_workspace_name(ws_id):
    ws_json = os.path.join(WORKSPACE_DIR, ws_id, "workspace.json")
    if os.path.exists(ws_json):
        with open(ws_json) as f:
            data = json.load(f)
            folder = data.get('folder', '')
            if folder.startswith('file://'):
                name = folder.split('/')[-1]
                name = name.replace('%3A', ':').replace('%', '')
                if name.startswith('/d'):
                    name = 'D:' + name[2:]
                elif name.startswith('/c'):
                    name = 'C:' + name[2:]
            else:
                name = folder
            return name
    return ws_id[:12]

# Build workspace map
print("Building workspace map...")
ws_map = {}
ws_data = {}
for ws_id in sorted(os.listdir(WORKSPACE_DIR)):
    name = get_workspace_name(ws_id)
    ws_map[ws_id] = name
    ws_data[ws_id] = {'name': name, 'prompts': []}

print(f"Found {len(ws_map)} workspaces")

# Extract user prompts from all workspaceStorage
print("\nExtracting user prompts from workspaceStorage...")
total_prompts = 0
for ws_id in sorted(os.listdir(WORKSPACE_DIR)):
    db_path = os.path.join(WORKSPACE_DIR, ws_id, "state.vscdb")
    if not os.path.exists(db_path):
        continue
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM ItemTable WHERE [key] = 'icube-ai-agent-storage-input-history'")
        row = cursor.fetchone()
        if row and row[0]:
            try:
                history = json.loads(row[0])
                if isinstance(history, list):
                    for entry in history:
                        prompt_text = entry.get('inputText', '')
                        ws_data[ws_id]['prompts'].append({
                            'text': prompt_text,
                            'parsedQuery': entry.get('parsedQuery', []),
                            'images': entry.get('images', []),
                            'multiMedia': entry.get('multiMedia', []),
                        })
                        total_prompts += 1
            except json.JSONDecodeError:
                pass
        conn.close()
    except:
        pass

print(f"Extracted {total_prompts} user prompts")

# Parse Git commits from snapshot repos
print("\nParsing Git commits from snapshot repos...")
all_commits = []
session_count = 0

for session in sorted(os.listdir(SNAPSHOT_BASE)):
    git_dir = os.path.join(SNAPSHOT_BASE, session, "v2", ".git")
    objects_dir = os.path.join(git_dir, "objects")

    if not os.path.exists(objects_dir):
        continue

    session_count += 1
    for subdir in os.listdir(objects_dir):
        if subdir in ['info', 'pack']:
            continue
        subdir_path = os.path.join(objects_dir, subdir)
        if not os.path.isdir(subdir_path):
            continue
        for obj_name in os.listdir(subdir_path):
            obj_path = os.path.join(subdir_path, obj_name)
            try:
                content = read_obj(obj_path)
                obj_type, body = parse_obj(content)
                if obj_type == 'commit':
                    text = body.decode('utf-8', errors='replace')
                    lines = text.split('\n')
                    c = {
                        'session': session,
                        'hash': (subdir + obj_name),
                        'author_type': None,
                        'msg_type': None,
                        'timestamp': None,
                        'message': None,
                        'tree': None,
                        'parent': None,
                    }
                    for line in lines:
                        if line.startswith('author '):
                            parts = line.split()
                            for i, p in enumerate(parts):
                                if p.startswith('<') and i+1 < len(parts) and parts[i+1].isdigit():
                                    c['timestamp'] = int(parts[i+1])
                            if 'trae-user' in line:
                                c['author_type'] = 'user'
                            elif 'trae-ai-agent' in line:
                                c['author_type'] = 'agent'
                            elif 'trae-system' in line:
                                c['author_type'] = 'system'
                        elif line.startswith('tree '):
                            c['tree'] = line.split()[1]
                        elif line.startswith('parent '):
                            c['parent'] = line.split()[1]
                        elif line.strip() and not line.startswith('    '):
                            msg = line.strip()
                            if msg.startswith('user-'):
                                c['msg_type'] = 'user_message'
                            elif msg.startswith('toolcall-'):
                                c['msg_type'] = 'toolcall'
                            elif msg.startswith('before-chat-'):
                                c['msg_type'] = 'before_chat'
                            elif msg.startswith('after-chat-'):
                                c['msg_type'] = 'after_chat'
                            elif msg == 'init empty branch':
                                c['msg_type'] = 'init'
                            c['message'] = msg
                    all_commits.append(c)
            except:
                pass

all_commits.sort(key=lambda x: x.get('timestamp', 0))
print(f"Parsed {len(all_commits)} commits from {session_count} sessions")

# Build conversation sessions
print("\nBuilding conversation sessions...")
sessions = []
current_session = None
turns = []
prompt_index = {}

for c in all_commits:
    session = c['session']

    if session != current_session:
        if turns:
            sessions.append({
                'session_id': session,
                'workspace': ws_map.get(current_session, current_session[:12]),
                'turns': turns,
                'total_turns': len(turns),
                'user_message_count': sum(1 for t in turns if t['type'] == 'user_message'),
            })
        current_session = session
        turns = []
        prompt_index = {}  # Reset for new session

    if c['msg_type'] == 'user_message':
        ts = datetime.datetime.fromtimestamp(c['timestamp']).strftime('%Y-%m-%d %H:%M:%S') if c['timestamp'] else ''
        # Try to find prompt from workspace input history
        prompt_text = ''
        for p in ws_data.get(session, {}).get('prompts', []):
            if p['text']:
                prompt_text = p['text']
                break

        turns.append({
            'type': 'user_message',
            'timestamp': ts,
            'commit_hash': c['hash'][:12],
            'prompt': prompt_text,
            'raw_message': c['message'],
            'tree': c['tree'][:12] if c.get('tree') else None,
        })
    elif c['msg_type'] == 'toolcall':
        ts = datetime.datetime.fromtimestamp(c['timestamp']).strftime('%Y-%m-%d %H:%M:%S') if c['timestamp'] else ''
        turns.append({
            'type': 'toolcall',
            'timestamp': ts,
            'commit_hash': c['hash'][:12],
            'toolcall_id': c['message'],
            'tree': c['tree'][:12] if c.get('tree') else None,
        })
    elif c['msg_type'] == 'before_chat':
        turns.append({
            'type': 'before_chat',
            'timestamp': datetime.datetime.fromtimestamp(c['timestamp']).strftime('%Y-%m-%d %H:%M:%S') if c['timestamp'] else '',
            'tag': c['message'],
        })
    elif c['msg_type'] == 'after_chat':
        turns.append({
            'type': 'after_chat',
            'timestamp': datetime.datetime.fromtimestamp(c['timestamp']).strftime('%Y-%m-%d %H:%M:%S') if c['timestamp'] else '',
            'tag': c['message'],
        })
    elif c['msg_type'] == 'init':
        turns.append({
            'type': 'init',
            'timestamp': datetime.datetime.fromtimestamp(c['timestamp']).strftime('%Y-%m-%d %H:%M:%S') if c['timestamp'] else '',
        })

if turns:
    sessions.append({
        'session_id': current_session,
        'workspace': ws_map.get(current_session, current_session[:12]),
        'turns': turns,
        'total_turns': len(turns),
        'user_message_count': sum(1 for t in turns if t['type'] == 'user_message'),
    })

print(f"Built {len(sessions)} conversation sessions")

# Save results
result = {
    'extraction_info': {
        'date': datetime.datetime.now().isoformat(),
        'source': 'Trae CN - workspaceStorage + ai-agent snapshot Git repos',
        'total_sessions': len(sessions),
        'total_user_messages': sum(s.get('user_message_count', 0) for s in sessions),
        'total_git_commits': len(all_commits),
        'total_prompts_extracted': total_prompts,
        'note': 'AI responses not locally stored in readable format (stored in binary database.db)',
    },
    'sessions': sessions,
    'workspace_summary': [
        {'workspace_id': ws_id, 'name': data['name'], 'prompt_count': len(data['prompts'])}
        for ws_id, data in ws_data.items()
        if len(data['prompts']) > 0
    ],
}

os.makedirs(OUTPUT_DIR, exist_ok=True)
output_file = os.path.join(OUTPUT_DIR, "trae_conversations.json")
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\nSaved to: {output_file}")

# Show sample
print(f"\n{'='*70}")
print(f"SAMPLE - First 5 sessions:")
sample_sessions = [s for s in sessions if s.get('user_message_count', 0) > 0][:5]
for s in sample_sessions:
    print(f"\nSession {s['session_id'][:12]} | {s['workspace']} | {s['user_message_count']} user messages")
    user_msgs = [t for t in s['turns'] if t['type'] == 'user_message']
    for t in user_msgs[:3]:
        prompt = t.get('prompt', t.get('raw_message', ''))
        print(f"  {t['timestamp']} | {prompt[:100]}")

# Also create a simple prompt-only extraction for easy reading
prompts_only = []
for ws_id, data in ws_data.items():
    for p in data['prompts']:
        if p['text']:
            prompts_only.append({
                'workspace': data['name'],
                'workspace_id': ws_id,
                'prompt': p['text'],
                'files_referenced': [fq.get('relatePath', '') for fq in p.get('parsedQuery', []) if fq.get('relatePath')],
            })

prompts_file = os.path.join(OUTPUT_DIR, "trae_prompts_only.json")
with open(prompts_file, 'w', encoding='utf-8') as f:
    json.dump(prompts_only, f, ensure_ascii=False, indent=2)

print(f"\nPrompts-only extraction: {len(prompts_only)} prompts saved to {prompts_file}")