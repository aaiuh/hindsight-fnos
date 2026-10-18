#!/usr/bin/env python3
"""入口页服务：给应用中心一个可内嵌的页面，并把接口文档同源转发过去。

飞牛应用中心的 iframe 入口通过 gatewaySocket 把 /app/<应用名> 反向代理到
本 socket，且把这段前缀原样透传。直接把这个路径交给静态文件服务，会去找
<页面目录>/app/<应用名>/index.html，于是点开图标只看到「文件未找到」。

所以这里做三件事：
  1. 收到请求先剥掉 /app/<应用名> 前缀
  2. /info.json 由服务端去问一次 API 的健康状态（页面不跨域直连端口）
  3. /backend/* 转发到本机 API，这样接口文档在应用内也能打开，
     不必从浏览器直连 API 端口

用法：serve.py <socket 路径>
环境变量：HINDSIGHT_API_PORT（默认 8888）、HINDSIGHT_APP_NAME（默认 Hindsight）
"""
from __future__ import annotations

import http.client
import http.server
import json
import os
import re
import socketserver
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
API_PORT = int(os.environ.get("HINDSIGHT_API_PORT", "8888"))
APP_NAME = os.environ.get("HINDSIGHT_APP_NAME", "Hindsight")
MOUNT = "/app/" + APP_NAME
BACKEND = "/backend/"
TIMEOUT = 120


def api_healthy() -> bool:
    try:
        conn = http.client.HTTPConnection("127.0.0.1", API_PORT, timeout=3)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        resp.read()
        conn.close()
        return 200 <= resp.status < 300
    except Exception:  # noqa: BLE001 —— 健康检查失败就是不可用
        return False


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE, **kwargs)

    def log_message(self, format, *args):  # noqa: A002
        sys.stderr.write("ui - %s\n" % (format % args))

    # ── 路径处理 ──────────────────────────────────────────────
    def _normalize(self):
        path, sep, query = self.path.partition("?")
        if path.startswith(MOUNT):
            path = path[len(MOUNT):] or "/"
        elif path.startswith("/app/"):
            rest = path[len("/app/"):]
            cut = rest.find("/")
            path = "/" if cut < 0 else rest[cut:]
        if path in ("", "/"):
            path = "/index.html"
        self.path = path + (("?" + query) if sep else "")

    def _wants_backend(self) -> bool:
        return self.path.split("?", 1)[0].startswith(BACKEND)

    # ── 各方法 ────────────────────────────────────────────────
    def do_GET(self):
        self._normalize()
        path = self.path.split("?", 1)[0]
        if path in ("/health", "/healthz"):
            return self._json({"status": "ok"})
        if path in ("/info.json", "/info"):
            return self._json(
                {"name": APP_NAME, "port": API_PORT, "api_ok": api_healthy()}
            )
        if self._wants_backend():
            return self._proxy()
        return super().do_GET()

    def do_HEAD(self):
        self._normalize()
        if self._wants_backend():
            return self._proxy()
        return super().do_HEAD()

    def do_POST(self):
        self._normalize()
        if self._wants_backend():
            return self._proxy()
        return self.send_error(405)

    def do_PUT(self):
        self.do_POST()

    def do_PATCH(self):
        self.do_POST()

    def do_DELETE(self):
        self.do_POST()

    # ── 转发到本机 API ────────────────────────────────────────
    def _proxy(self):
        sub = self.path[len(BACKEND) - 1:]  # 保留前导 /
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "connection", "accept-encoding")
        }
        try:
            conn = http.client.HTTPConnection("127.0.0.1", API_PORT, timeout=TIMEOUT)
            conn.request(self.command, sub, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            ctype = resp.getheader("Content-Type", "application/octet-stream")
        except Exception as exc:  # noqa: BLE001
            return self._json({"error": "后端不可达", "detail": str(exc)}, status=502)

        # 接口文档页把 openapi.json 写成了绝对路径，转发后要改成相对，
        # 否则会指到网关根路径上。
        if ctype.startswith("text/html"):
            text = data.decode("utf-8", "replace")
            text = text.replace('"/openapi.json"', '"openapi.json"')
            text = text.replace("'/openapi.json'", "'openapi.json'")
            # Swagger UI 默认入口是 /docs，脚本里也可能写绝对路径
            text = text.replace("/docs/oauth2-redirect", "oauth2-redirect")
            data = text.encode("utf-8")
        elif ctype.startswith("application/json") and sub.startswith("/openapi.json"):
            try:
                doc = json.loads(data)
                doc["servers"] = [{"url": MOUNT + BACKEND.rstrip("/")}]
                data = json.dumps(doc, ensure_ascii=False).encode("utf-8")
            except Exception:  # noqa: BLE001
                pass

        self.send_response(resp.status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)
        conn.close()

    # ── 工具 ──────────────────────────────────────────────────
    def _json(self, obj, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


class UnixHTTPServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def get_request(self):
        request, _ = super().get_request()
        return request, ("unix", 0)


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: serve.py <socket 路径>", file=sys.stderr)
        return 2
    sock_path = sys.argv[1]
    try:
        os.unlink(sock_path)
    except FileNotFoundError:
        pass

    httpd = UnixHTTPServer(sock_path, Handler)
    os.chmod(sock_path, 0o666)
    sys.stderr.write("ui: listening on %s (%s -> 127.0.0.1:%d)\n" % (sock_path, BACKEND, API_PORT))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        try:
            os.unlink(sock_path)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
