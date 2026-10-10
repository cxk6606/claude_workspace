"""运行后在浏览器页面里不断弹出很多话语。

用法:
    python3 popup.py              # 启动并自动打开浏览器
    python3 popup.py --no-browser # 只启动服务，手动访问网址
    python3 popup.py --port 9000  # 指定端口
按 Ctrl+C 退出。
"""
import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

MESSAGES = [
    "今天也要加油哦！",
    "记得多喝水 💧",
    "你已经做得很棒了",
    "休息一下，看看远处",
    "保持好心情 😊",
    "天天开心",
    "别熬夜，早点睡",
    "慢慢来，比较快",
    "你比自己想象的更厉害",
    "今天的你也很闪亮 ✨",
    "吃点好吃的吧 🍜",
    "做自己就很好",
    "一切都会好起来的",
    "深呼吸，放松肩膀",
    "有进步就值得庆祝 🎉",
]

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>话语弹窗</title>
<style>
  html, body { margin: 0; height: 100%; overflow: hidden;
               background: #1f2430; font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif; }
  #hint { position: fixed; inset: auto 0 12px 0; text-align: center;
          color: #8b93a7; font-size: 13px; pointer-events: none; }
  .bubble { position: absolute; padding: 14px 22px; border-radius: 14px;
            color: #2b2b2b; font-size: 20px; font-weight: 600; white-space: nowrap;
            box-shadow: 0 6px 18px rgba(0,0,0,.35);
            animation: pop .35s ease-out, fade .6s ease-in forwards;
            animation-delay: 0s, var(--life); }
  @keyframes pop  { from { transform: scale(.3); opacity: 0; } to { transform: scale(1); opacity: 1; } }
  @keyframes fade { to { opacity: 0; transform: translateY(-20px); } }
</style>
</head>
<body>
<div id="hint">点击页面可以立即多弹一批 · 关闭标签页即停止</div>
<script>
const MESSAGES = __MESSAGES__;
const COLORS = ["#ffd166", "#ef9fbc", "#9bf6ff", "#caffbf", "#ffc6ff", "#fdffb6", "#a0c4ff"];
const pick = a => a[Math.floor(Math.random() * a.length)];

function spawn() {
  const el = document.createElement("div");
  el.className = "bubble";
  el.textContent = pick(MESSAGES);
  el.style.background = pick(COLORS);
  el.style.left = Math.random() * 80 + "vw";
  el.style.top = Math.random() * 85 + "vh";
  el.style.setProperty("--life", (2.5 + Math.random() * 2).toFixed(1) + "s");
  document.body.appendChild(el);
  el.addEventListener("animationend", e => { if (e.animationName === "fade") el.remove(); });
}

function burst(n) { for (let i = 0; i < n; i++) setTimeout(spawn, i * 60); }

burst(12);
setInterval(() => spawn(), 250);
document.addEventListener("click", () => burst(15));
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        body = PAGE.replace("__MESSAGES__", json.dumps(MESSAGES, ensure_ascii=False)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="在浏览器页面弹出很多话语")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"已启动: {url}  (Ctrl+C 退出)")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
