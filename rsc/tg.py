"""Minimal Telegram Bot API client with optional SOCKS5 proxy.

The SOCKS5 handshake is done by hand (RFC 1928/1929) so no third-party
package is needed. Host names are resolved by the proxy (socks5h
behaviour), which matters where local DNS for api.telegram.org is
poisoned.
"""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import struct
from urllib.parse import unquote, urlsplit

MAX_TEXT = 4096


class TelegramError(Exception):
    def __init__(self, description: str, code: int = 0):
        super().__init__(description)
        self.code = code


def _recv(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise OSError("SOCKS5 proxy closed the connection")
        buf += chunk
    return buf


def socks5_connect(proxy: str, host: str, port: int, timeout: float) -> socket.socket:
    url = urlsplit(proxy)
    if url.scheme not in ("socks5", "socks5h"):
        raise ValueError(f"unsupported proxy scheme {url.scheme!r} (use socks5://)")
    sock = socket.create_connection((url.hostname, url.port or 1080), timeout=timeout)
    try:
        user, password = unquote(url.username or ""), unquote(url.password or "")
        methods = b"\x00\x02" if user else b"\x00"
        sock.sendall(bytes([5, len(methods)]) + methods)
        _, method = _recv(sock, 2)
        if method == 2:
            ub, pb = user.encode(), password.encode()
            sock.sendall(bytes([1, len(ub)]) + ub + bytes([len(pb)]) + pb)
            if _recv(sock, 2)[1] != 0:
                raise OSError("SOCKS5 proxy rejected the username/password")
        elif method != 0:
            raise OSError("SOCKS5 proxy accepts none of our auth methods")
        hb = host.encode("idna")
        sock.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + struct.pack(">H", port))
        reply = _recv(sock, 4)
        if reply[1] != 0:
            raise OSError(f"SOCKS5 connect to {host}:{port} failed (code {reply[1]})")
        atyp = reply[3]
        size = 4 if atyp == 1 else 16 if atyp == 4 else _recv(sock, 1)[0]
        _recv(sock, size + 2)
        return sock
    except BaseException:
        sock.close()
        raise


def request(url: str, data: bytes | None = None, proxy: str = "", timeout: float = 30,
            headers: dict | None = None) -> tuple[int, bytes]:
    """One HTTP(S) request, through the SOCKS5 proxy when given."""
    u = urlsplit(url)
    https = u.scheme == "https"
    port = u.port or (443 if https else 80)
    if proxy:
        sock = socks5_connect(proxy, u.hostname, port, timeout)
    else:
        sock = socket.create_connection((u.hostname, port), timeout=timeout)
    sock.settimeout(timeout)
    if https:
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=u.hostname)
        conn = http.client.HTTPSConnection(u.hostname, port, timeout=timeout)
    else:
        conn = http.client.HTTPConnection(u.hostname, port, timeout=timeout)
    conn.sock = sock
    try:
        path = (u.path or "/") + ("?" + u.query if u.query else "")
        conn.request("POST" if data is not None else "GET", path, body=data,
                     headers={"User-Agent": "remote-server-control", **(headers or {})})
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def split_text(text: str, limit: int = MAX_TEXT) -> list[str]:
    """Split on line breaks so HTML tags of one line stay together."""
    parts, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:limit])
            line = line[limit:]
        if cur and len(cur) + 1 + len(line) > limit:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur or not parts:
        parts.append(cur)
    return parts


class Telegram:
    def __init__(self, token: str, proxy: str = ""):
        self.token = token
        self.proxy = proxy

    def call(self, method: str, http_timeout: float = 30, **params):
        status, body = request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=json.dumps(params).encode(), proxy=self.proxy, timeout=http_timeout,
            headers={"Content-Type": "application/json"},
        )
        try:
            res = json.loads(body)
        except ValueError:
            raise TelegramError(f"HTTP {status}: not JSON", status) from None
        if not res.get("ok"):
            raise TelegramError(res.get("description", f"HTTP {status}"), res.get("error_code", status))
        return res["result"]

    def send(self, chat_id, text: str, **kw):
        kw.setdefault("parse_mode", "HTML")
        kw.setdefault("disable_web_page_preview", True)
        parts = split_text(text)
        last = None
        for i, part in enumerate(parts):
            extra = kw if i == len(parts) - 1 else {k: v for k, v in kw.items() if k != "reply_markup"}
            last = self.call("sendMessage", chat_id=chat_id, text=part, **extra)
        return last

    def edit(self, chat_id, message_id, text: str, **kw):
        kw.setdefault("parse_mode", "HTML")
        kw.setdefault("disable_web_page_preview", True)
        try:
            return self.call("editMessageText", chat_id=chat_id, message_id=message_id,
                             text=split_text(text)[0], **kw)
        except TelegramError as exc:
            if "not modified" in str(exc):
                return None
            raise
