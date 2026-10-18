#!/usr/bin/env python3
"""Hindsight 入口服务：把官方管理控制台搬到本机，并统一两个入口。

控制台（Control Plane）是上游自带的 Next.js 应用，只能绑本机回环地址
（它用绑定地址做同源校验，绑 0.0.0.0 会让每个页面重定向到自己）。所以：

    Control Plane  → 127.0.0.1:<CP_PORT>
    本服务         → Unix socket（应用中心内嵌） + 0.0.0.0:<UI_PORT>（内网直连）
                                       ↓ 反向代理，含流式响应
                                 127.0.0.1:<CP_PORT>

用法：serve.py <socket 路径>
环境变量：
  HINDSIGHT_CP_PORT    控制台内部端口（默认 9998）
  HINDSIGHT_UI_PORT     对外端口（默认 9999）
  HINDSIGHT_APP_NAME    应用名（默认 Hindsight）
"""
from __future__ import annotations

import http.client
import http.server
import os
import socketserver
import sys
import threading

CP_HOST = "127.0.0.1"
CP_PORT = int(os.environ.get("HINDSIGHT_CP_PORT", "9998"))
UI_PORT = int(os.environ.get("HINDSIGHT_UI_PORT", "9999"))
APP_NAME = os.environ.get("HINDSIGHT_APP_NAME", "Hindsight")
CP_AVAILABLE = os.environ.get("HINDSIGHT_CP_AVAILABLE", "1") != "0"
MOUNT = "/app/" + APP_NAME

# 上游会拿绑定地址做同源比较，Host 头必须与它看到的一致
CP_HOST_HEADER = "localhost:%d" % CP_PORT

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

MISSING_NODE_PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hindsight 管理界面需要 Node.js</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#eef2f2;
color:#16211f;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;padding:24px}
.c{max-width:560px;padding:28px 30px;border-radius:18px;background:#fff;
box-shadow:0 18px 50px rgba(16,40,38,.10)}
h1{margin:0 0 10px;font-size:17px;font-weight:600}
p{margin:0 0 10px;font-size:13.5px;line-height:1.75;color:#5c6f6c}
code{background:#f1f5f4;padding:1px 6px;border-radius:6px;font-size:12.5px}
ul{margin:6px 0 0;padding-left:18px;font-size:13px;line-height:1.9;color:#5c6f6c}
</style></head><body><div class="c">
<h1>管理界面需要 Node.js</h1>
<p>本机的记忆服务已在正常运行，接口文档也可以正常访问。只有管理界面需要 Node.js 运行时。</p>
<p>处理方式：在应用中心安装 <b>Node.js</b>（v22 或 v24 均可），然后回到应用中心把本应用「停止」再「启动」，无需重装、数据不动。</p>
<ul>
<li>记忆服务：<code>http://&lt;NAS地址&gt;:API端口/docs</code></li>
<li>已装 Node.js 后本页会自动变成管理界面</li>
</ul>
</div></body></html>"""


STARTING_PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hindsight 正在启动</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#eef2f2;
color:#16211f;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.c{padding:30px 34px;border-radius:18px;background:#fff;box-shadow:0 18px 50px rgba(16,40,38,.10);text-align:center}
h1{margin:0 0 8px;font-size:17px;font-weight:600}
p{margin:0;font-size:13px;color:#5c6f6c}
</style></head><body><div class="c"><h1>Hindsight 正在启动</h1>
<p>控制台还没就绪，本页 5 秒后自动重试。</p></div>
<script>setTimeout(function(){location.reload()},5000)</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "hindsight-ui"

    def log_message(self, format, *args):  # noqa: A002
        sys.stderr.write("ui - %s\n" % (format % args))

    # ── 路径：剥掉网关挂载前缀 ────────────────────────────────
    def _path(self) -> str:
        raw = self.path
        if raw.startswith(MOUNT):
            rest = raw[len(MOUNT):]
            return rest or "/"
        if raw.startswith("/app/"):
            rest = raw[len("/app/"):]
            cut = rest.find("/")
            return "/" if cut < 0 else rest[cut:]
        return raw or "/"

    def _starting(self):
        body = (STARTING_PAGE if CP_AVAILABLE else MISSING_NODE_PAGE).encode()
        self.send_response(503)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if CP_AVAILABLE:
            self.send_header("Retry-After", "5")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # ── 转发 ──────────────────────────────────────────────────
    def _proxy(self):
        path = self._path()
        mounted = self.path.startswith(MOUNT) or self.path.startswith("/app/")
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        headers = {}
        for k, v in self.headers.items():
            if k.lower() in HOP_BY_HOP or k.lower() in ("host", "accept-encoding"):
                continue
            headers[k] = v
        headers["Host"] = CP_HOST_HEADER

        conn = None
        try:
            conn = http.client.HTTPConnection(CP_HOST, CP_PORT, timeout=180)
            conn.request(self.command, path, body=body, headers=headers)
            resp = conn.getresponse()
        except Exception as exc:  # noqa: BLE001
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
            sys.stderr.write("ui - 控制台不可达：%s\n" % exc)
            return self._starting()

        try:
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                lk = k.lower()
                if lk in HOP_BY_HOP or lk == "content-length":
                    continue
                if lk == "location" and mounted and v.startswith("/"):
                    # 网关内嵌时，跳转必须带回挂载前缀，否则会跳到 NAS 根路径
                    v = MOUNT + v
                self.send_header(k, v)
            clen = resp.getheader("Content-Length")
            if clen:
                self.send_header("Content-Length", clen)
            elif self.command == "HEAD":
                self.send_header("Content-Length", "0")
            else:
                # 长度未知：交回 HTTP/1.0 式关闭连接，边读边写
                self.close_connection = True
            self.end_headers()

            if self.command != "HEAD":
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write("ui - 转发中断：%s\n" % exc)
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _handle(self):
        if self.path.split("?", 1)[0] == MOUNT:
            # 少了结尾斜杠，页面里的相对路径会算错
            self.send_response(301)
            self.send_header("Location", MOUNT + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._proxy()

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _handle


class UnixHTTPServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def get_request(self):
        request, _ = super().get_request()
        return request, ("unix", 0)


class TCPHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: serve.py <socket 路径>", file=sys.stderr)
        return 2
    sock_path = sys.argv[1]
    try:
        os.unlink(sock_path)
    except FileNotFoundError:
        pass

    unix_srv = UnixHTTPServer(sock_path, Handler)
    os.chmod(sock_path, 0o666)
    threading.Thread(target=unix_srv.serve_forever, daemon=True).start()

    tcp_srv = None
    try:
        tcp_srv = TCPHTTPServer(("0.0.0.0", UI_PORT), Handler)
        threading.Thread(target=tcp_srv.serve_forever, daemon=True).start()
        listen = "0.0.0.0:%d" % UI_PORT
    except OSError as exc:
        sys.stderr.write("ui: %d 端口不可用（%s），仅保留应用内入口\n" % (UI_PORT, exc))
        listen = "(仅 socket)"

    sys.stderr.write(
        "ui: socket=%s  listen=%s  ->  %s:%d\n" % (sock_path, listen, CP_HOST, CP_PORT)
    )
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for srv in (tcp_srv, unix_srv):
            if srv is not None:
                srv.shutdown()
                srv.server_close()
        try:
            os.unlink(sock_path)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
