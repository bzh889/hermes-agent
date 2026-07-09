"""Capture the actual Authorization header Claude Code sends."""
import json, ssl, sys, os
from http.server import HTTPServer, BaseHTTPRequestHandler

CREDS_PATH = "C:/Users/mtk12265/.claude/.credentials.json"
CERT_DIR = os.environ.get('TEMP', 'C:/Users/mtk12265/AppData/Local/Temp')
OUT_PATH = os.path.join(CERT_DIR, "captured_claude_headers.json")

class CaptureHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        cl = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(cl) if cl else b''
        result = {
            "headers": dict(self.headers),
            "path": self.path,
            "body_keys": list(json.loads(body).keys()) if body else [],
        }
        with open(OUT_PATH, 'w') as f:
            json.dump(result, f, indent=2)
        # Respond
        self.send_response(200)
        self.send_header('content-type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"id":"msg_ok","type":"message","role":"assistant","content":[{"type":"text","text":"CAPTURED"}],"model":"claude-sonnet-4-6","stop_reason":"end_turn","usage":{"input_tokens":10,"output_tokens":1}}')
    def log_message(self, *a): pass

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(
    os.path.join(CERT_DIR, 'capture_cert.pem'),
    os.path.join(CERT_DIR, 'capture_key.pem'),
)
srv = HTTPServer(('127.0.0.1', 45679), CaptureHandler)
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
srv.handle_request()
srv.server_close()
