"""Loopback-only UI demo. No real OTPs, model calls, or persistent storage.

Run with Python, then start CRA with REACT_APP_API_URL=http://127.0.0.1:8011.
Only test number 9999000099 and code 123456 are accepted.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from secrets import token_urlsafe
from urllib.parse import urlsplit

account = {"user_id": "+919999000099", "crops": [], "onboarded_at": None}
messages = []
sessions = set()


class Demo(BaseHTTPRequestHandler):
    def reply(self, body, status=200):
        self.send_response(status)
        origin = self.headers.get("Origin", "")
        if origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_OPTIONS(self):
        self.reply({})

    def handle_request(self):
        global account
        path = urlsplit(self.path).path
        size = int(self.headers.get("Content-Length", 0))
        if size > 100000:
            return self.reply({"detail": "Text-only demo; attachments are disabled."}, 413)
        raw = self.rfile.read(size) if size else b"{}"
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError):
            return self.reply({"detail": "Text-only demo; attachments are disabled."}, 400)
        if path == "/health":
            return self.reply({"status": "ok", "mode": "local simulated demo"})
        if path == "/auth/request-code":
            if body.get("phone") != "9999000099":
                return self.reply({"detail": "Use demo number 9999000099."}, 400)
            print("LOCAL DEMO sign-in code: 123456 (no SMS sent)", flush=True)
            return self.reply({"sent": False, "phone": "+91 ***** 00099", "transport": "console", "expires_in": 600})
        if path == "/auth/verify":
            if body.get("phone") != "9999000099" or body.get("code") != "123456":
                return self.reply({"detail": "Use demo number 9999000099 and code 123456."}, 401)
            token = token_urlsafe(24)
            sessions.add(token)
            return self.reply({"token": token, "user": account, "needs_onboarding": not account["onboarded_at"]})
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if token not in sessions:
            return self.reply({"detail": "Sign in to the local demo."}, 401)
        if path == "/auth/me":
            return self.reply({"user": account, "needs_onboarding": not account["onboarded_at"]})
        if path == "/history":
            return self.reply({"messages": messages})
        if path == "/agent":
            answer = "**Local demo — simulated answer, not farming advice.**\n\nYour question reached the demo API. You can now complete or skip the farm details below, ask another question, refresh, and sign out."
            messages.extend([{"direction": "inbound", "body": body.get("query", "")}, {"direction": "outbound", "body": answer}])
            return self.reply({"answer": answer, "tools_used": [], "reply_language": "en-IN"})
        if path == "/profile" and self.command == "PUT":
            account.update({k: v for k, v in body.items() if k in {"name", "district", "state", "crops", "area", "area_unit"} and v is not None})
            account["onboarded_at"] = "demo-completed"
            return self.reply({"saved": True, "user": account})
        if path == "/auth/signout":
            sessions.clear()
            return self.reply({"signed_out": True})
        return self.reply({"detail": "This feature is not available in the local demo."}, 404)

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request


if __name__ == "__main__":
    print("Local demo API: http://127.0.0.1:8011 — test number 9999000099 / code 123456", flush=True)
    HTTPServer(("127.0.0.1", 8011), Demo).serve_forever()
