#!/usr/bin/env python3
"""Hindsight 应用服务：管理界面 + 接口转发。

同时监听两个入口：
  * Unix socket —— 应用中心内嵌（/app/Hindsight/），网关把前缀原样透传
  * TCP 端口   —— 内网直连（默认 9999）

页面用同源相对路径请求本服务，由本服务再去访问本机 API，
这样无论从应用中心打开还是内网直连，都不需要浏览器能直连 API 端口。

用法：serve.py <socket 路径>
环境变量：
  HINDSIGHT_API_PORT   API 端口（默认 8888）
  HINDSIGHT_UI_PORT    内网直连端口（默认 9999）
  HINDSIGHT_APP_NAME   应用名（默认 Hindsight）
"""
from __future__ import annotations

import http.client
import http.server
import json
import os
import socketserver
import sys
import threading
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
API_HOST = "127.0.0.1"
API_PORT = int(os.environ.get("HINDSIGHT_API_PORT", "8888"))
UI_PORT = int(os.environ.get("HINDSIGHT_UI_PORT", "9999"))
APP_NAME = os.environ.get("HINDSIGHT_APP_NAME", "Hindsight")
MOUNT = "/app/" + APP_NAME


def api_call(method: str, path: str, body=None, timeout: int = 120):
    """访问本机 Hindsight API，返回 (status, bytes, content_type)。"""
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection(API_HOST, API_PORT, timeout=timeout)
    try:
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read(), resp.getheader(
            "Content-Type", "application/octet-stream"
        )
    finally:
        conn.close()


def api_json(method: str, path: str, body=None, timeout: int = 120):
    """返回 (json, error)。错误统一成字符串，方便直接回给页面。"""
    try:
        status, raw, _ = api_call(method, path, body, timeout)
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    if status >= 400:
        return None, "HTTP %d" % status
    try:
        return json.loads(raw), None
    except Exception:  # noqa: BLE001
        return None, "响应格式异常"


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE, **kwargs)

    def log_message(self, format, *args):  # noqa: A002
        sys.stderr.write("ui - %s\n" % (format % args))

    # ── 路径处理 ──────────────────────────────────────────────
    def _strip_mount(self) -> str:
        path, sep, query = self.path.partition("?")
        if path.startswith(MOUNT):
            path = path[len(MOUNT):] or "/"
        elif path.startswith("/app/"):
            rest = path[len("/app/"):]
            cut = rest.find("/")
            path = "/" if cut < 0 else rest[cut:]
        self.path = path + (("?" + query) if sep else "")
        return path

    def _query(self) -> dict:
        q = urllib.parse.urlparse(self.path).query
        return {k: v[-1] for k, v in urllib.parse.parse_qs(q).items()}

    # ── 各方法 ────────────────────────────────────────────────
    def do_GET(self):
        raw = self.path.split("?", 1)[0]
        if raw == MOUNT:  # 少了结尾斜杠，页面里的相对路径会算错
            self.send_response(301)
            self.send_header("Location", MOUNT + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        path = self._strip_mount()
        if path == "/api/overview":
            return self._overview()
        if path == "/api/memories":
            return self._memories()
        if path == "/api/memory":
            return self._memory()
        if path == "/api/health":
            return self._health()
        if path.startswith("/backend/"):
            return self._proxy()
        if path in ("/", "/index.html", "/index.htm"):
            self.path = "/index.html"
        return super().do_GET()

    def do_HEAD(self):
        self._strip_mount()
        if self.path.startswith("/backend/"):
            return self._proxy()
        return super().do_HEAD()

    def do_POST(self):
        self._strip_mount()
        if self.path.startswith("/backend/"):
            return self._proxy()
        self.send_error(405)

    do_PUT = do_PATCH = do_DELETE = do_POST

    # ── 业务接口 ──────────────────────────────────────────────
    def _overview(self):
        banks, err = api_json("GET", "/v1/default/banks", timeout=20)
        if err:
            return self._json({"ok": False, "error": err}, 502)
        out = []
        for b in banks.get("banks") or []:
            out.append(
                {
                    "id": b.get("bank_id"),
                    "name": b.get("name") or b.get("bank_id"),
                    "mission": b.get("mission") or "",
                    "facts": b.get("fact_count") or 0,
                    "last_write": b.get("last_write_at"),
                }
            )
        return self._json({"ok": True, "banks": out})

    def _memories(self):
        q = self._query()
        bank = q.get("bank") or ""
        if not bank:
            return self._json({"ok": False, "error": "缺少 bank"}, 400)
        params = {"limit": q.get("limit", "50"), "offset": q.get("offset", "0")}
        for key in ("q", "type", "state"):
            if q.get(key):
                params[key] = q[key]
        path = "/v1/default/banks/%s/memories/list?%s" % (
            urllib.parse.quote(bank, safe=""),
            urllib.parse.urlencode(params),
        )
        data, err = api_json("GET", path, timeout=60)
        if err:
            return self._json({"ok": False, "error": err}, 502)
        items = []
        for m in data.get("items") or []:
            items.append(
                {
                    "id": m.get("id"),
                    "text": m.get("text") or "",
                    "fact_type": m.get("fact_type"),
                    "date": m.get("date") or m.get("mentioned_at"),
                    "entities": m.get("entities") or [],
                    "document_id": m.get("document_id"),
                    "context": m.get("context") or "",
                }
            )
        return self._json(
            {"ok": True, "total": data.get("total") or 0, "items": items}
        )

    def _memory(self):
        q = self._query()
        bank, mid = q.get("bank") or "", q.get("id") or ""
        if not bank or not mid:
            return self._json({"ok": False, "error": "缺少参数"}, 400)
        path = "/v1/default/banks/%s/memories/%s" % (
            urllib.parse.quote(bank, safe=""),
            urllib.parse.quote(mid, safe=""),
        )
        data, err = api_json("GET", path, timeout=30)
        if err:
            return self._json({"ok": False, "error": err}, 502)
        return self._json({"ok": True, "memory": data})

    def _health(self):
        try:
            status, _, _ = api_call("GET", "/health", timeout=5)
            ok = status == 200
        except Exception:  # noqa: BLE001
            ok = False
        return self._json({"ok": ok, "api_port": API_PORT, "ui_port": UI_PORT})

    # ── 接口转发（接口文档用）────────────────────────────────
    def _proxy(self):
        sub = self.path[len("/backend"):] or "/"
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "connection", "accept-encoding")
        }
        conn = None
        try:
            conn = http.client.HTTPConnection(API_HOST, API_PORT, timeout=120)
            conn.request(self.command, sub, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            ctype = resp.getheader("Content-Type", "application/octet-stream")
            status = resp.status
        except Exception as exc:  # noqa: BLE001
            return self._json({"error": "后端不可达", "detail": str(exc)}, 502)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

        # 文档页把 openapi.json 写成绝对路径，转发后要改成相对，
        # 否则会指到网关根路径上。
        if ctype.startswith("text/html"):
            text = data.decode("utf-8", "replace")
            text = text.replace('"/openapi.json"', '"openapi.json"')
            text = text.replace("'/openapi.json'", "'openapi.json'")
            text = text.replace("/docs/oauth2-redirect", "oauth2-redirect")
            data = text.encode("utf-8")
        elif ctype.startswith("application/json") and sub.startswith("/openapi.json"):
            try:
                doc = json.loads(data)
                doc["servers"] = [{"url": MOUNT + "/backend"}]
                data = json.dumps(doc, ensure_ascii=False).encode("utf-8")
            except Exception:  # noqa: BLE001
                pass

        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    # ── 工具 ──────────────────────────────────────────────────
    def _json(self, obj, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
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
        "ui: socket=%s  listen=%s  api=%s:%d\n"
        % (sock_path, listen, API_HOST, API_PORT)
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
