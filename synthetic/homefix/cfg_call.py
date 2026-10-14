# Runs inside v210-config: calls the local config service with its own basic-auth token, prints status + body only.
import base64, json, os, sys, urllib.request, urllib.error
sys.path.insert(0, "/app")
for kv in open("/proc/1/environ", "rb").read().split(b"\0"):
    if b"=" in kv:
        k, v = kv.decode(errors="ignore").split("=", 1)
        os.environ.setdefault(k, v)
import settings.base as b
cls = next(c for c in vars(b).values() if isinstance(c, type) and hasattr(c, "AUTH_TOKENS"))
method, path, kind = sys.argv[1], sys.argv[2], sys.argv[3]
body = sys.stdin.read() if method in ("POST", "PUT", "PATCH") else None
acc, user = ("u2s", "superAdmin") if kind == "admin" else ("s2s", "console")
tok = sorted(cls.AUTH_TOKENS[acc][user])[0]
req = urllib.request.Request("http://localhost:5002" + path, data=body.encode() if body else None, method=method)
req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{tok}".encode()).decode())
req.add_header("Content-Type", "application/json")
req.add_header("X-CLIENT-AUTH-ID", os.environ.get("CALL_AUTH_ID", "<AUTH_ID>"))
try:
    r = urllib.request.urlopen(req, timeout=60); print(r.status); print(r.read().decode())
except urllib.error.HTTPError as e:
    print(e.code); print(e.read().decode())
