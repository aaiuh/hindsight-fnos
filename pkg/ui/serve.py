#!/usr/bin/env python3
"""极小的静态页服务，监听 Unix socket，供应用中心内嵌。

飞牛应用中心的 iframe 入口通过 gatewaySocket 把 /app/<应用> 反向代理到
本 socket。服务根路径没有页面时，点开桌面图标只会看到 API 的
{"detail":"Not Found"}，所以这里补一个入口页。

用法：serve.py <socket 路径>
环境变量：HINDSIGHT_API_PORT —— 供页面拼出接口文档地址
"""
from __future__ import annotations

import http.server
import json
import os
import socket
import socketserver
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
API_PORT = os.environ.get("HINDSIGHT_API_PORT", "8888")
TIMEOUT = 30


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE, **kwargs)

    def log_message(self, format, *args):  # noqa: A002  少写日志
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _normalize(self):
        """应用中心会把 /app/<应用名> 这个挂载前缀原样透传给后端。

        不剥掉它，静态服务就会去找 <页面目录>/app/Hindsight/index.html，
        于是点开图标看到的是 Python http.server 的 404 错误页。
        """
        path, sep, query = self.path.partition("?")
        if path.startswith("/app/"):
            rest = path[len("/app/"):]
            cut = rest.find("/")
            path = "/" if cut < 0 else rest[cut:]
        if path in ("", "/"):
            path = "/index.html"
        self.path = path + (("?" + query) if sep else "")

    def do_GET(self):
        self._normalize()
        path = self.path.split("?", 1)[0]
        if path in ("/health", "/healthz"):
            return self._json({"status": "ok"})
        if path in ("/info.json", "/info"):
            return self._json({"port": API_PORT, "name": "Hindsight"})
        return super().do_GET()

    def do_HEAD(self):
        self._normalize()
        return super().do_HEAD()

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # 应用中心内嵌时不允许被缓存，避免改版后仍显示旧页
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


class UnixHTTPServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

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
    sys.stderr.write("ui: listening on %s\n" % sock_path)
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
