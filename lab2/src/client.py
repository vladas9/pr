import os
import socket
import sys

def recv_all(sock: socket.socket) -> bytes:
    chunks = []
    while True:
        data = sock.recv(4096)
        if not data:
            break
        chunks.append(data)
    return b"".join(chunks)

def main():
    if len(sys.argv) != 5:
        print("Usage: python client.py server_host server_port url_path directory")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])
    url_path = sys.argv[3]
    outdir = sys.argv[4]

    req = (
        f"GET {url_path} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("iso-8859-1")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        sock.sendall(req)
        raw = recv_all(sock)

    sep = b"\r\n\r\n"
    idx = raw.find(sep)
    if idx == -1:
        print("Invalid response (no headers/body separator).")
        sys.exit(1)

    header_bytes, body = raw[:idx], raw[idx+4:]
    headers = header_bytes.decode("iso-8859-1", errors="replace").split("\r\n")

    status_line = headers[0] if headers else "HTTP/1.0 000 Unknown"
    print(f"[client] {status_line}")

    content_type = ""
    for h in headers[1:]:
        if h.lower().startswith("content-type:"):
            content_type = h.split(":", 1)[1].strip().lower()
            break

    if status_line.split()[1] != "200":
        try:
            print(body.decode("utf-8", errors="replace"))
        except Exception:
            print(body)
        sys.exit(0)

    if content_type.startswith("text/html"):
        print(body.decode("utf-8", errors="replace"))
    elif content_type.startswith("image/png"):
        os.makedirs(outdir, exist_ok=True)
        fname = os.path.basename(url_path.rstrip("/")) or "index.png"
        if not fname.lower().endswith(".png"):
            fname += ".png"
        path = os.path.join(outdir, fname)
        with open(path, "wb") as f:
            f.write(body)
        print(f"[client] saved PNG -> {path}")
    elif content_type.startswith("application/pdf"):
        os.makedirs(outdir, exist_ok=True)
        fname = os.path.basename(url_path.rstrip("/")) or "file.pdf"
        if not fname.lower().endswith(".pdf"):
            fname += ".pdf"
        path = os.path.join(outdir, fname)
        with open(path, "wb") as f:
            f.write(body)
        print(f"[client] saved PDF -> {path}")
    else:
        print("[client] unknown or unsupported content-type; dumping first 200 bytes:")
        print(body[:200])

if __name__ == "__main__":
    main()
