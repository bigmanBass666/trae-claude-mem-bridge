import urllib.request
import json

# Test Worker HTTP API directly
def test_api(endpoint, method="GET", body=None):
    url = f"http://localhost:37777{endpoint}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

# Test health
print("Testing /health...")
result = test_api("/health")
print(f"Health: {result}")

# Test stats
print("\nTesting /api/stats...")
result = test_api("/api/stats")
print(f"Stats: {json.dumps(result, indent=2, ensure_ascii=False)[:500]}")

# Test observations
print("\nTesting /api/observations...")
result = test_api("/api/observations?limit=3")
obs = result.get("observations", [])
print(f"Observations count: {len(obs)}")
for o in obs[:3]:
    print(f"  - [{o.get('id')}] {o.get('type')} | platform: {o.get('platform_source')} | project: {o.get('project')}")

# Test session/summarize
print("\nTesting /api/sessions/summarize...")
result = test_api("/api/sessions/summarize", method="POST", body={
    "contentSessionId": "manual-test-001",
    "last_assistant_message": "这是一条测试摘要"
})
print(f"Summarize: {result}")
