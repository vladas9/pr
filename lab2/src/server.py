import os
import socket
import threading
import time
from collections import defaultdict, deque
from http_utils import http_date_now, parse_request_line, safe_path, split_headers_body, guess_mime

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "dir_listing.html")
HOST = "0.0.0.0"
PORT = 8080
SERVER_NAME = "ServerHTTP/2.0"

request_counts = defaultdict(int)
counter_lock = threading.Lock()

rate_limit = defaultdict(lambda: deque(maxlen=5))
rate_lock = threading.Lock()
RATE = 5
WINDOW = 1.0


def respond(status_code: int, reason: str, body: bytes, mime: str = "text/html; charset=utf-8") -> bytes:
    return (
        f"HTTP/1.0 {status_code} {reason}\r\n"
        f"Date: {http_date_now()}\r\n"
        f"Server: {SERVER_NAME}\r\n"
        f"Content-Type: {mime}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode() + body


def respond_text(code: int, msg: str) -> bytes:
    body = f"<html><body><h1>{code} {msg}</h1></body></html>".encode()
    return respond(code, msg, body)

def normalize_path(target: str, is_dir: bool) -> str:
    if not target.startswith("/"):
        target = "/" + target
    if is_dir and not target.endswith("/"):
        target += "/"
    if not is_dir and target.endswith("/"):
        target = target.rstrip("/")
    return target


def increment_request_count(target: str,is_dir: bool, safe=True):
    key = normalize_path(target, is_dir)

    if safe:
        with counter_lock:
            request_counts[target] += 1
    else:
        c = request_counts[target]
        time.sleep(0.01)
        request_counts[target] = c + 1


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    with rate_lock:
        q = rate_limit[ip]
        while q and now - q[0] > WINDOW:
            q.popleft()
        if len(q) >= RATE:
            return True
        q.append(now)
        return False


def directory_listing_html(req_path: str, fs_dir: str, root: str) -> bytes:
    try:
        items = sorted(os.listdir(fs_dir))
    except OSError:
        return respond_text(404, "Not Found")

    if not req_path.endswith("/"):
        req_path += "/"

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    list_items = []

    if os.path.realpath(fs_dir) != os.path.realpath(root):
        parts = req_path.rstrip("/").split("/")
        parent = "/".join(parts[:-1])
        if not parent:
            parent = "/"
        elif not parent.endswith("/"):
            parent += "/"
        list_items.append(f'<li class="dir"><a href="{parent}">..</a></li>')

    for name in items:
        href = req_path + name
        full = os.path.join(fs_dir, name)
        if os.path.isdir(full):
            href += "/"
        count = request_counts[href]
        if os.path.isdir(full):
            list_items.append(f'<li class="dir"><a href="{href}">{name}/</a> ({count})</li>')
        else:
            list_items.append(f'<li class="file"><a href="{href}">{name}</a> ({count})</li>')

    body_html = template.replace("{{path}}", req_path).replace("{{items}}", "\n".join(list_items))
    return respond(200, "OK", body_html.encode("utf-8"))


def serve_file(fs_path: str) -> bytes:
    mime = guess_mime(fs_path)
    try:
        with open(fs_path, "rb") as f:
            data = f.read()
    except OSError:
        return respond_text(404, "Not Found")
    return respond(200, "OK", data, mime)


def handle(conn: socket.socket, root: str):
    try:
        conn.settimeout(5)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk

        headers, _ = split_headers_body(data)
        lines = headers.split(b"\r\n")
        if not lines:
            conn.sendall(respond_text(400, "Bad Request"))
            return

        method, target, version = parse_request_line(lines[0].decode(errors="replace"))
        if method != "GET":
            conn.sendall(respond_text(405, "Method Not Allowed"))
            return

        ip = conn.getpeername()[0]
        if is_rate_limited(ip):
            conn.sendall(respond_text(429, "Too Many Requests"))
            return

        time.sleep(1)  

        fs_path, is_dir = safe_path(root, target)
        if not fs_path:
            conn.sendall(respond_text(404, "Not Found"))
            return

        if is_dir and not target.endswith("/"):
            target += "/"
        increment_request_count(target,is_dir, safe=True)

        resp = directory_listing_html(target, fs_path, root) if is_dir else serve_file(fs_path)
        conn.sendall(resp)

    except Exception as e:
        print("Error:", e)
        try:
            conn.sendall(respond_text(500, "Internal Server Error"))
        except Exception:
            pass
    finally:
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", help="Directory to serve")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    root = os.path.abspath(args.directory)
    print(f"Serving '{root}' on http://0.0.0.0:{args.port}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, args.port))
        s.listen(10)

        while True:
            conn, addr = s.accept()
            print(f"Connection from {addr}")
            t = threading.Thread(target=handle, args=(conn, root), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
