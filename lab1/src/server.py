import os
import socket
from typing import Tuple
from http_utils import http_date_now, parse_request_line, safe_path, split_headers_body, guess_mime

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "dir_listing.html")
HOST = "0.0.0.0"
PORT = 8080
SERVER_NAME = "DaygerHTTP/2.0"

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
            list_items.append(f'<li class="dir"><a href="{href}">{name}/</a></li>')
        else:
            list_items.append(f'<li class="file"><a href="{href}">{name}</a></li>')

    body_html = template.replace("{{path}}", req_path).replace("{{items}}", "\n".join(list_items))
    return respond(200, "OK", body_html.encode("utf-8"), mime="text/html; charset=utf-8")

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

        req_line = lines[0].decode(errors="replace")
        method, target, version = parse_request_line(req_line)
        if not method or not target:
            conn.sendall(respond_text(400, "Bad Request"))
            return
        if method != "GET":
            conn.sendall(respond_text(405, "Method Not Allowed"))
            return

        fs_path, is_dir = safe_path(root, target)
        if not fs_path:
            conn.sendall(respond_text(404, "Not Found"))
            return

        if is_dir:
            resp = directory_listing_html(target, fs_path, root)
        else:
            resp = serve_file(fs_path)

        conn.sendall(resp)
    finally:
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        conn.close()

# ---------- SERVER LOOP ----------
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
        s.listen(5)
        while True:
            conn, addr = s.accept()
            print(f"Connection from {addr}")
            handle(conn, root)

if __name__ == "__main__":
    main()
