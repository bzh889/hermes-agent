"""Spike 001: Can Python's http.server start a static file server in 3 lines?"""
import http.server, socketserver, threading

PORT = 18412

# --- The 3-line server ---
handler = http.server.SimpleHTTPRequestHandler  # line 1
with socketserver.TCPServer(("", PORT), handler) as httpd:  # line 2
    print(f"Serving on http://localhost:{PORT}/")  # line 3
    # Keep alive for test
    threading.Timer(3.0, httpd.shutdown).start()
    httpd.serve_forever()
