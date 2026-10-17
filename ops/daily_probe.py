"""The daily live model probe. Cost is bounded by the application's gates."""
import json
import os
import urllib.request

url = os.environ["HEALTH_URL"].removesuffix("/health") + "/ask"
request = urllib.request.Request(url, data=json.dumps({"question": "Is ACC-4471 part of a ring, and how does the money move?", "depth": 1}).encode(), headers={"Authorization": "Bearer " + os.environ["JUDGE_KEY"], "Content-Type": "application/json", "Accept": "text/event-stream"})
answers = []
with urllib.request.urlopen(request, timeout=120) as response:
    content_type = response.headers.get("Content-Type", "")
    if "text/event-stream" in content_type:
        for line in response:
            if line.startswith(b"data:"):
                data = json.loads(line[5:].strip())
                if isinstance(data, dict) and ("shape" in data or "answer" in data):
                    answers.append(data.get("answer", data))
    else:
        answers.append(json.load(response))
assert answers, "Daily investigation did not return an answer"
answer=answers[-1]
assert answer.get("shape", answer.get("outcome")) in {"answered_with_path","answered_from_memory"} and answer.get("path_edges"), "Daily investigation did not return an evidenced path"
print("Daily depth-one investigation: " + answer["shape"])
