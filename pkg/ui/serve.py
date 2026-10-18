#!/usr/bin/env python3
"""依赖提示页（仅在官方控制台无法启动时使用）。

管理界面本体是上游的 Control Plane，原样运行、不做任何改写。
只有当系统缺少 Node.js、或运行时包里没有控制台时，本服务才会占用界面端口，
把「缺什么、怎么补」讲清楚，避免用户点开图标看到一个打不开的端口。

正常路径下这个服务不会被启动，也不会替代官方界面。

环境变量：
  HINDSIGHT_UI_PORT   界面端口（默认 9999）
  HINDSIGHT_API_PORT  API 端口（默认 8888），用于在页面上给出接口文档地址
"""
from __future__ import annotations

import http.server
import json
import os
import sys

UI_PORT = int(os.environ.get("HINDSIGHT_UI_PORT", "9999"))
API_PORT = int(os.environ.get("HINDSIGHT_API_PORT", "8888"))

PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hindsight 需要 Node.js</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f3f5f9;
color:#16211f;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;padding:24px}}
.c{{max-width:580px;padding:28px 30px;border-radius:18px;background:#fff;
box-shadow:0 18px 50px rgba(16,40,38,.10)}}
h1{{margin:0 0 10px;font-size:17px;font-weight:600}}
p{{margin:0 0 10px;font-size:13.5px;line-height:1.75;color:#5c6f6c}}
code{{background:#eef2f1;padding:1px 6px;border-radius:6px;font-size:12.5px}}
ul{{margin:6px 0 0;padding-left:18px;font-size:13px;line-height:1.9;color:#5c6f6c}}
</style></head><body><div class="c">
<h1>管理界面需要 Node.js</h1>
<p>记忆服务已经在运行，REST/MCP 接口也正常。只有管理界面需要 Node.js 运行时（20 及以上，建议 22 / 24）。</p>
<p>处理方式：在应用中心安装 <b>Node.js</b>，然后回到应用中心把本应用「停止」再「启动」，无需重装、数据不动。</p>
<ul>
<li>接口文档：<code>http://&lt;NAS地址&gt;:{api}/docs</code></li>
<li>接口端口：<code>{api}</code>，界面端口：<code>{ui}</code></li>
</ul>
</div></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002
        sys.stderr.write("notice - %s\n" % (format % args))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/health", "/healthz"):
            return self._send(json.dumps({"ok": True}).encode(), "application/json")
        if path in ("/api/health",):
            return self._send(json.dumps({"ok": False, "reason": "console-unavailable"}).encode(),
                              "application/json")
        body = PAGE.format(api=API_PORT, ui=UI_PORT).encode()
        self._send(body, "text/html; charset=utf-8")

    do_HEAD = do_GET

    def _send(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def main() -> int:
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", UI_PORT), Handler)
    sys.stderr.write("notice: 依赖提示页监听 0.0.0.0:%d\n" % UI_PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
