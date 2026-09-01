import json, subprocess
out = subprocess.run(["gh","api","repos/Epslion404/ENeuron/issues/6/comments"], capture_output=True, encoding="utf-8", errors="replace")
data = json.loads(out.stdout)
for c in data:
    print("=== id", c["id"], c["user"]["login"], c["created_at"], "===")
    print(c["body"])
    print()