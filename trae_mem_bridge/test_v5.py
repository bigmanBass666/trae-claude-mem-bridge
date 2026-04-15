"""
Test v5 - 全面验证源码审查后的改进
"""
import sys
sys.path.insert(0, 'D:/Test/trae_message_extraction/trae_mem_bridge')
from mcp_server import handle_hook_event, _is_internal_message, SKIP_TOOLS

print("=" * 60)
print("Test v5: Source code audit fixes")
print("=" * 60)

# Test 1: SKIP_TOOLS
print("\n--- Test 1: SKIP_TOOLS client-side filtering ---")
skip_result = handle_hook_event({
    'event': 'PostToolUse',
    'payload': {
        'session_id': 'TRAE-V5-TEST',
        'cwd': 'D:/Test/trae_message_extraction',
        'tool_name': 'TodoWrite',
        'tool_input': {'todos': []},
        'tool_response': 'OK'
    }
})
print(f"  TodoWrite: {skip_result['content'][0]['text']}")
assert 'Skipped' in skip_result['content'][0]['text'], "Should skip TodoWrite!"

# MCP tools should also be skipped
skip_mcp = handle_hook_event({
    'event': 'PostToolUse',
    'payload': {
        'session_id': 'TRAE-V5-TEST',
        'cwd': 'D:/Test/trae_message_extraction',
        'tool_name': 'trae_mem_hook_event',
        'tool_input': {},
        'tool_response': 'OK'
    }
})
print(f"  trae_mem_hook_event: {skip_mcp['content'][0]['text']}")
assert 'Skipped' in skip_mcp['content'][0]['text'], "Should skip own MCP tools!"

# Non-skip tool should pass
pass_result = handle_hook_event({
    'event': 'PostToolUse',
    'payload': {
        'session_id': 'TRAE-V5-TEST',
        'cwd': 'D:/Test/trae_message_extraction',
        'tool_name': 'Read',
        'tool_input': {'file_path': '/test.py'},
        'tool_response': 'print("hello")'
    }
})
print(f"  Read: {pass_result['content'][0]['text']}")
assert 'captured' in pass_result['content'][0]['text'].lower() or 'Tool' in pass_result['content'][0]['text'], "Should capture Read!"

# Test 2: Empty prompt filtering
print("\n--- Test 2: Empty prompt filtering ---")
empty_result = handle_hook_event({
    'event': 'UserPromptSubmit',
    'payload': {
        'session_id': 'TRAE-V5-TEST',
        'cwd': 'D:/Test/trae_message_extraction',
        'prompt': ''
    }
})
print(f"  Empty prompt: {empty_result['content'][0]['text']}")
assert 'Skipped' in empty_result['content'][0]['text'], "Should skip empty prompt!"

# Test 3: Internal message filtering
print("\n--- Test 3: Internal message filtering ---")
internal = handle_hook_event({
    'event': 'UserPromptSubmit',
    'payload': {
        'session_id': 'TRAE-V5-TEST',
        'cwd': 'D:/Test/trae_message_extraction',
        'prompt': '<task-notification><task-id>abc</task-id><status>completed</status></task-notification>'
    }
})
print(f"  Internal msg: {internal['content'][0]['text']}")
assert 'Skipped' in internal['content'][0]['text'], "Should skip internal message!"

# Test 4: Summarize with last_assistant_message (HTTP API path)
print("\n--- Test 4: Summarize with last_assistant_message ---")
summarize_result = handle_hook_event({
    'event': 'Stop',
    'payload': {
        'session_id': 'TRAE-V5-TEST',
        'cwd': 'D:/Test/trae_message_extraction',
        'last_assistant_message': '完成了Trae-Claude-Mem桥接器的v5版本，修复了8个问题。'
    }
})
print(f"  Summarize: {summarize_result['content'][0]['text']}")

# Test 5: SessionEnd (HTTP API path)
print("\n--- Test 5: SessionEnd via HTTP API ---")
end_result = handle_hook_event({
    'event': 'SessionEnd',
    'payload': {
        'session_id': 'TRAE-V5-TEST',
        'cwd': 'D:/Test/trae_message_extraction'
    }
})
print(f"  SessionEnd: {end_result['content'][0]['text']}")

# Test 6: SKIP_TOOLS set contents
print(f"\n--- Test 6: SKIP_TOOLS = {len(SKIP_TOOLS)} tools ---")
for t in sorted(SKIP_TOOLS):
    print(f"  - {t}")

print("\n" + "=" * 60)
print("All v5 tests completed!")
print("=" * 60)
