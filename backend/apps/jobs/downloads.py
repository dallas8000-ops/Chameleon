"""Credential-free, exact-origin HTTPS downloads with a pinned public TCP peer."""
import http.client
import ipaddress
import queue
import re
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit

from django.conf import settings


class DownloadRejected(Exception):
    def __init__(self, code="result_download_policy"):
        self.code = code
        super().__init__(code)


def host_for_url(url):
    if not isinstance(url, str) or len(url) > 8192 or re.search(r"[\x00-\x20\x7f\\]", url):
        raise DownloadRejected()
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or parsed.fragment or not host
                or not re.fullmatch(r"[a-zA-Z0-9]+(?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", host)):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError
        if "." not in host or ".." in host or "%" in parsed.netloc:
            raise ValueError
    except ValueError:
        raise DownloadRejected() from None
    return host.lower(), parsed


def authorized_origins():
    values = getattr(settings, "GENERATION_DOWNLOAD_ORIGINS", [])
    if not isinstance(values, (list, tuple)):
        return set()
    origins = set()
    try:
        for value in values:
            host, parsed = host_for_url(value)
            if parsed.path not in ("", "/") or parsed.query:
                return set()
            origins.add(host)
    except DownloadRejected:
        return set()
    return origins


def public_ip(value):
    try:
        ip = ipaddress.ip_address(value)
        # Reject transition mechanisms as well as non-public destinations.
        return ip.is_global and not ip.is_multicast and not (
            isinstance(ip, ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.sixtofour or ip.teredo)
        )
    except ValueError:
        return False


def resolve(host, deadline):
    result = queue.Queue(maxsize=1)
    def lookup():
        try:
            result.put(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
        except OSError:
            result.put(None)
    # A stuck system resolver must not prevent the worker deadline from being honored.
    threading.Thread(target=lookup, daemon=True).start()
    try:
        answers = result.get(timeout=max(0.001, min(5, deadline - time.monotonic())))
    except queue.Empty:
        raise DownloadRejected("result_download_failed") from None
    if not answers:
        raise DownloadRejected("result_download_failed")
    return list({answer[4][0] for answer in answers})


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, deadline):
        super().__init__(host, port=443, timeout=5, context=ssl.create_default_context())
        self.address, self.deadline = address, deadline

    def connect(self):
        # No proxy, hostname re-resolution, HTTP tunnel, or alternate peer fallback.
        family = socket.AF_INET6 if ":" in self.address else socket.AF_INET
        raw = socket.socket(family, socket.SOCK_STREAM)
        self.transport_socket = raw
        try:
            raw.settimeout(max(0.001, min(5, self.deadline - time.monotonic())))
            raw.connect((self.address, 443))
            peer = raw.getpeername()[0]
            if ipaddress.ip_address(peer) != ipaddress.ip_address(self.address) or not public_ip(peer):
                raise DownloadRejected()
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
            self.transport_socket = self.sock
            self.sock.settimeout(max(0.001, min(10, self.deadline - time.monotonic())))
        except Exception:
            raw.close()
            raise


def download_image(url, target):
    deadline = time.monotonic() + 60
    host, parsed = host_for_url(url)
    if host not in authorized_origins():
        raise DownloadRejected()
    addresses = resolve(host, deadline)
    if not addresses or any(not public_ip(address) for address in addresses):
        raise DownloadRejected()
    connection = PinnedHTTPSConnection(host, sorted(addresses)[0], deadline)
    def abort():
        # HTTPConnection may detach its socket for a Connection: close response.
        sock = getattr(connection, "transport_socket", None) or connection.sock
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()
    timer = threading.Timer(max(0.001, deadline - time.monotonic()), abort)
    timer.daemon = True
    timer.start()
    try:
        connection.request("GET", (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
                           headers={"Accept-Encoding": "identity", "Accept": "image/png,image/jpeg,image/webp"})
        response = connection.getresponse()
        # Redirects (including same-origin) are never followed.
        if response.status != 200:
            raise DownloadRejected("result_download_failed" if response.status in (403, 404, 429) or response.status >= 500 else "result_download_policy")
        if response.getheader("Content-Encoding", "identity").lower() not in ("", "identity"):
            raise DownloadRejected()
        declared = response.getheader("Content-Length")
        limit = min(25 * 1024 * 1024, getattr(settings, "STUDIO_MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
        if declared is not None and (not declared.isdigit() or not 0 < int(declared) <= limit):
            raise DownloadRejected("result_invalid_media")
        size = 0
        while True:
            if time.monotonic() >= deadline:
                raise DownloadRejected("result_download_failed")
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise DownloadRejected("result_invalid_media")
            target.write(chunk)
        if not size or (declared is not None and size != int(declared)):
            raise DownloadRejected("result_invalid_media")
        return (response.getheader("Content-Type", "") or "").split(";")[0].strip().lower()
    except (OSError, http.client.HTTPException, ValueError):
        raise DownloadRejected("result_download_failed") from None
    finally:
        timer.cancel()
        connection.close()
