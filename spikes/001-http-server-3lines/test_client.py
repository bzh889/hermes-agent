"""Client: verify the 3-line static server actually serves files."""
import httpx, time, subprocess, sys, os

PORT = 18412

# Start server in background (doesn't auto-shutdown — we kill it)
server_code = f"""
import http.server, socketserver
handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", {PORT}), handler) as httpd:
    print("READY", flush=True)
    httpd.serve_forever()
"""
server = subprocess.Popen(
    [sys.executable, "-c", server_code],
    cwd=os.path.join(os.getcwd(), "spikes", "001-http-server-3lines"),
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True,
)

# Wait for READY signal
line = server.stdout.readline().strip()
print(f"Server stdout: {line}")
time.sleep(0.5)

try:
    r = httpx.get(f"http://localhost:{PORT}/index.html", verify=False)
    print(f"Status:   {r.status_code}")
    print(f"Contains: {'Spike 001' in r.text}")
    print(f"Body:\n{r.text}")
except Exception as e:
    print(f"FAIL: {e}")
finally:
    server.terminate()
    server.wait(timeout=3)
    print(f"Server exit: {server.returncode}")
