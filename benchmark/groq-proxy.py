"""Lightweight proxy that truncates tools to 128 before forwarding to LiteLLM.

Groq's API has a hard limit of 128 tools. Claude Code sends 150+.
This proxy sits between Claude Code and LiteLLM, trimming the tools list.

Usage:
    python3 benchmark/groq-proxy.py  (listens on :4001, forwards to LiteLLM on :4000)
"""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

import httpx

# Hardcoded localhost-only — this proxy only forwards to the local LiteLLM instance
_LITELLM_BASE = "http://127.0.0.1:4000"
MAX_TOOLS = 128
LISTEN_PORT = 4001

# Core tools that Claude Code needs — keep these, drop the rest
PRIORITY_TOOLS = {
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "Agent", "Skill", "WebFetch", "WebSearch",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
    "NotebookEdit", "LSP", "EnterPlanMode", "ExitPlanMode",
}

# Allowlisted paths — only forward known API paths
_ALLOWED_PATHS = {"/v1/messages", "/v1/messages/count_tokens", "/health/liveliness", "/health"}


def _build_url(path: str) -> str:
    """Build target URL from a validated path. Only allows known API paths."""
    clean = path.split("?")[0].rstrip("/")
    if clean not in _ALLOWED_PATHS:
        clean = "/v1/messages"  # default fallback
    return f"{_LITELLM_BASE}{clean}"


class ProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = None

        # Truncate tools if present
        if data and "tools" in data and len(data["tools"]) > MAX_TOOLS:
            tools = data["tools"]
            priority = [t for t in tools if t.get("name") in PRIORITY_TOOLS]
            others = [t for t in tools if t.get("name") not in PRIORITY_TOOLS]
            remaining = MAX_TOOLS - len(priority)
            data["tools"] = priority + others[:remaining]
            body = json.dumps(data).encode()

        url = _build_url(self.path)
        fwd_headers = {k: v for k, v in self.headers.items() if k.lower() != "host"}
        fwd_headers["Content-Length"] = str(len(body))

        with httpx.Client(timeout=300) as client:
            resp = client.post(url, content=body, headers=fwd_headers)

        self.send_response(resp.status_code)
        for k, v in resp.headers.items():
            if k.lower() not in ("transfer-encoding", "connection", "content-encoding"):
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp.content)

    def do_GET(self) -> None:
        url = _build_url(self.path)
        with httpx.Client(timeout=10) as client:
            resp = client.get(url)

        self.send_response(resp.status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(resp.content)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"[groq-proxy] {args[0]}\n")


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", LISTEN_PORT), ProxyHandler)
    print(f"Groq proxy listening on 127.0.0.1:{LISTEN_PORT}")
    print(f"Forwarding to LiteLLM at {_LITELLM_BASE}")
    print(f"Tools truncated to {MAX_TOOLS} (Groq limit)")
    server.serve_forever()
