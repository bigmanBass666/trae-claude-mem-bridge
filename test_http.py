import urllib.request
import json

url = "http://localhost:37777/api/sessions/summarize"
data = json.dumps({
    "contentSessionId": "test-session-123",
    "last_assistant_message": "这是一条测试摘要消息"
}).encode("utf-8")

req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(resp.read().decode("utf-8"))
except Exception as e:
    print(f"Error: {e}")
