"""Tiny web app for the Azure secure web app lab. Standard library only.

/health        liveness for the App Service health check
/secret-check  reports whether the Key Vault reference resolved. It never returns the secret.
"""
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", os.environ.get("WEBSITES_PORT", "8000")))


def secret_status():
    value = os.environ.get("DEMO_SECRET", "")
    if not value:
        return {"configured": False, "resolved": False}
    if value.startswith("@Microsoft.KeyVault"):
        # App Service could not resolve the reference, so the setting is still the reference text.
        return {"configured": True, "resolved": False}
    return {
        "configured": True,
        "resolved": True,
        "length": len(value),
        "sha256_prefix": hashlib.sha256(value.encode()).hexdigest()[:8],
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path == "/secret-check":
            status = secret_status()
            self._send(200 if status["resolved"] else 503, status)
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):  # keep the console log short
        print(fmt % args, flush=True)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
