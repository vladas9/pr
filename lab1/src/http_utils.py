import email.utils
import os
import urllib.parse
from typing import Tuple, Optional

ALLOWED_MIME = {
    ".html": "text/html; charset=utf-8",
    ".htm":  "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".svg":  "image/svg+xml",
    ".ico":  "image/x-icon",
    ".pdf":  "application/pdf",
    ".txt":  "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".xml":  "application/xml; charset=utf-8",
    ".mp4":  "video/mp4",
    ".webm": "video/webm",
    ".mp3":  "audio/mpeg",
    ".wav":  "audio/wav",
    ".ogg":  "audio/ogg",
}

def http_date_now() -> str:
    return email.utils.formatdate(usegmt=True)

def split_headers_body(raw: bytes) -> Tuple[bytes, bytes]:
    sep = b"\r\n\r\n"
    idx = raw.find(sep)
    return (raw[:idx], raw[idx+4:]) if idx != -1 else (raw, b"")

def parse_request_line(line: str):
    parts = line.strip().split()
    if len(parts) != 3:
        return None, None, None
    method, target, version = parts
    return method, target, version

def safe_path(root: str, url_path: Optional[str]) -> Tuple[str, bool]:
    if not url_path:
        return "", False

    path = urllib.parse.urlsplit(url_path).path
    path = urllib.parse.unquote(path)

    joined = os.path.normpath(os.path.join(root, path.lstrip("/")))
    root_real = os.path.realpath(root)
    joined_real = os.path.realpath(joined)

    if not joined_real.startswith(root_real):
        return "", False

    return joined_real, os.path.isdir(joined_real)

def guess_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return ALLOWED_MIME.get(ext, "application/octet-stream")
