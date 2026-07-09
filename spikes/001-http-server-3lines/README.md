# Spike 001: Python http.server 3 行靜態伺服器

**Question:** Python 的 `http.server` 能不能在 ≤3 行內起一個可以 serve 靜態檔案的伺服器？

## Approach

測試兩種方式：

1. **程式碼 3 行** — `SimpleHTTPRequestHandler` + `TCPServer` + `serve_forever()`
2. **CLI 一行** — `python -m http.server PORT`

## Results

| 方式 | 行數 | 結果 | HTTP 狀態 |
|------|------|------|-----------|
| 程式碼 3 行 | 3 | ✅ 成功 serve `index.html` | 200 |
| CLI 一行 | 1 | ✅ `python -m http.server 18413` | 200 |

### 程式碼 3 行版本

```python
handler = http.server.SimpleHTTPRequestHandler           # line 1
with socketserver.TCPServer(("", PORT), handler) as httpd:  # line 2
    httpd.serve_forever()                                 # line 3
```

### CLI 一行版本

```bash
python -m http.server 8000
```

## Verdict: VALIDATED ✅

### What worked
- **3 行程式碼**即可啟動完整靜態檔案伺服器
- **1 行 CLI** `python -m http.server` 更簡潔
- 自動處理目錄列表、MIME type、404
- 純 stdlib，零依賴

### What didn't
- `TCPServer` 預設不允許 port 重複佔用（需加 `allow_reuse_address = True`）
- 單執行緒，不適合正式環境
- 無 HTTPS、無 auth

### Surprises
- `python -m http.server` 本身就是零行程式碼的靜態伺服器，比 3 行更短
- Windows 上 `port` 被佔用不會自動釋放，測試要等幾秒

### Recommendation for the real build
- 快速本地開發用 `python -m http.server PORT` 即可
- 需要客製行為再加 `SimpleHTTPRequestHandler` 子類
- 正式環境不適用（單執行緒、無安全機制）
