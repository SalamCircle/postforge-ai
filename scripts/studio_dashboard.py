"""Local-only Content Studio dashboard; never sends credentials or publishes."""
import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
try:
    from . import content_studio as studio
except ImportError:
    import content_studio as studio

ASSETS = Path(__file__).resolve().parents[1] / "dashboard"

def model(root, start=None, days=30):
    return {"calendar": studio.calendar(root, start, days), "health": studio.report(root),
            "brief": studio.brief(root), "drafts": [studio.review(root, d["id"]) for d in studio.drafts(root)]}

def action(root, data):
    if not isinstance(data, dict):
        raise ValueError("Invalid request")
    cmd = data.get("action")
    if cmd == "brand":
        return studio.set_brand(root, data["brand"])
    if cmd == "draft":
        return studio.save_draft(root, data["draft"])
    if cmd == "import":
        return studio.import_plan(root, data["drafts"])
    name, expected = data.get("id"), data.get("digest")
    if cmd == "revise":
        if studio.digest(studio.read_draft(root, name)) != expected or data["draft"]["id"] != name:
            raise ValueError("Draft changed; reload before editing")
        return studio.save_draft(root, data["draft"], edit=True)
    if cmd == "schedule":
        return studio.schedule(root, name, data["local_time"], data["timezone"], expected)
    if cmd == "reschedule":
        if data.get("confirmation") != "RESCHEDULE":
            raise ValueError("Explicit reschedule confirmation required")
        return studio.schedule(root, name, data["local_time"], data["timezone"], expected, reschedule=True)
    if cmd == "approve":
        if data.get("confirmation") != "APPROVE":
            raise ValueError("Explicit approval required")
        return studio.approve(root, name, expected)
    if cmd == "export":
        if data.get("confirmation") != "QUEUE":
            raise ValueError("Explicit queue confirmation required")
        return studio.export(root, name, expected)
    if cmd in {"delete", "delete-many"}:
        if data.get("confirmation") != "DELETE DRAFTS":
            raise ValueError("Explicit deletion confirmation required")
        return studio.delete_draft(root, name, expected) if cmd == "delete" else studio.delete_plan(root, data["items"])
    if cmd == "archive":
        if data.get("confirmation") != "ARCHIVE":
            raise ValueError("Explicit archive confirmation required")
        return studio.archive(root, name, expected)
    if cmd == "cancel":
        if data.get("confirmation") != "CANCEL":
            raise ValueError("Explicit cancellation required")
        return studio.cancel_queue(root, name, expected)
    if cmd == "reuse":
        return studio.reuse(root, name)
    raise ValueError("Unsupported action")

def handler_for(root, token, authority):
    origin = "http://" + authority
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_data(self, code, body, mime):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def json_response(self, code, obj):
            self.send_data(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def valid_host(self):
            return self.headers.get("Host") == authority

        def do_GET(self):
            if not self.valid_host():
                return self.json_response(403, {"error": "Invalid host"})
            parsed = urlsplit(self.path)
            paths = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8") }
            try:
                if parsed.path == "/logo.svg":
                    return self.send_data(200, (ASSETS.parent / "docs" / "assets" / "logo-v2.svg").read_bytes(), "image/svg+xml")
                if parsed.path in paths:
                    name, mime = paths[parsed.path]
                    body = (ASSETS / name).read_bytes()
                    if name == "index.html":
                        body = body.replace(b"__SESSION_TOKEN__", token.encode())
                    return self.send_data(200, body, mime)
                if parsed.path == "/api/model":
                    if self.headers.get("X-Studio-Token") != token:
                        return self.json_response(403, {"error": "Session required"})
                    q = parse_qs(parsed.query)
                    return self.json_response(200, model(root, q.get("start", [None])[0], int(q.get("days", ["30"])[0])))
                return self.json_response(404, {"error": "Not found"})
            except (ValueError, OSError, KeyError, TypeError):
                return self.json_response(400, {"error": "Unable to read workspace; check local data"})

        def do_POST(self):
            if not self.valid_host() or self.headers.get("Origin") != origin or self.headers.get("X-Studio-Token") != token:
                return self.json_response(403, {"error": "Invalid session or origin"})
            if self.path != "/api/action" or self.headers.get_content_type() != "application/json":
                return self.json_response(415, {"error": "Expected JSON action"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 100000:
                    raise ValueError("Request size outside limit")
                data = json.loads(self.rfile.read(size))
                return self.json_response(200, action(root, data))
            except (ValueError, OSError, KeyError, TypeError) as exc:
                return self.json_response(400, {"error": str(exc) if isinstance(exc, ValueError) else "Action refused; check workspace"})
    return Handler

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port from 1024 to 65535")
    authority = "127.0.0.1:" + str(args.port)
    server = HTTPServer(("127.0.0.1", args.port), handler_for(studio.ROOT, secrets.token_urlsafe(32), authority))
    print("Open http://" + authority + " in your browser. Local workspace only; Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
