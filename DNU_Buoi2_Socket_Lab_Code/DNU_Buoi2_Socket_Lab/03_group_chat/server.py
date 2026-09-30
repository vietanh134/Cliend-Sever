"""Bài 3 - Server phòng chat nhiều người bằng TCP + threading.

Protocol cơ bản:
- Server gửi NAME?
- Client trả username
- Server trả OK|... hoặc ERROR|...
- Sau đó mỗi dòng client gửi là một tin nhắn.
- /quit để rời phòng.
"""

import socket
import threading

HOST = "0.0.0.0"
PORT = 5002
ENCODING = "utf-8"
MAX_CLIENTS = 20

clients: dict[socket.socket, str] = {}
clients_lock = threading.Lock()
send_lock = threading.Lock()


def send_line(sock: socket.socket, text: str) -> None:
    sock.sendall((text + "\n").encode(ENCODING))


def recv_line(sock: socket.socket, max_bytes: int = 4096) -> str | None:
    data = bytearray()
    while len(data) < max_bytes:
        chunk = sock.recv(1)
        if not chunk:
            return None if not data else data.decode(ENCODING)
        if chunk == b"\n":
            return data.decode(ENCODING).rstrip("\r")
        data.extend(chunk)
    raise ValueError("Tin nhắn quá dài.")


def username_exists(username: str) -> bool:
    with clients_lock:
        return username.casefold() in {name.casefold() for name in clients.values()}


def broadcast(text: str, exclude: socket.socket | None = None) -> None:
    with clients_lock:
        targets = [sock for sock in clients if sock is not exclude]

    dead_clients: list[socket.socket] = []
    with send_lock:
        for sock in targets:
            try:
                send_line(sock, text)
            except OSError:
                dead_clients.append(sock)

    for sock in dead_clients:
        remove_client(sock, announce=False)


def remove_client(sock: socket.socket, announce: bool = True) -> None:
    with clients_lock:
        username = clients.pop(sock, None)

    try:
        sock.close()
    except OSError:
        pass

    if username and announce:
        print(f"[LEAVE] {username}")
        broadcast(f"[HỆ THỐNG] {username} đã rời phòng.")


def handle_client(client_socket: socket.socket, client_address: tuple[str, int]) -> None:
    username: str | None = None
    try:
        send_line(client_socket, "NAME?")
        proposed = recv_line(client_socket)
        if proposed is None:
            return

        username = proposed.strip()
        if not username or len(username) > 20 or "|" in username:
            send_line(client_socket, "ERROR|Tên phải có 1-20 ký tự và không chứa '|'.")
            return
        if username_exists(username):
            send_line(client_socket, "ERROR|Tên này đang được sử dụng.")
            return

        with clients_lock:
            if len(clients) >= MAX_CLIENTS:
                send_line(client_socket, "ERROR|Phòng chat đã đầy.")
                return
            clients[client_socket] = username

        send_line(client_socket, f"OK|Chào mừng {username}. Gõ /quit để rời phòng.")
        print(f"[JOIN] {username} từ {client_address[0]}:{client_address[1]}")
        broadcast(f"[HỆ THỐNG] {username} đã vào phòng.", exclude=client_socket)

        while True:
            message = recv_line(client_socket)
            if message is None:
                break

            message = message.strip()
            if not message:
                continue
            if message.lower() == "/quit":
                break

            print(f"[{username}] {message}")
            broadcast(f"[{username}] {message}", exclude=client_socket)

    except (ConnectionError, OSError, UnicodeError, ValueError) as exc:
        print(f"[ERROR] {client_address}: {exc}")
    finally:
        remove_client(client_socket, announce=username is not None)


def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(MAX_CLIENTS)

        print(f"[SERVER] Group chat đang lắng nghe tại 0.0.0.0:{PORT}")
        print(f"[SERVER] Tối đa {MAX_CLIENTS} client. Nhấn Ctrl+C để dừng.\n")

        while True:
            client_socket, client_address = server.accept()
            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address),
                daemon=True,
            )
            thread.start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[SERVER] Đang đóng các kết nối...")
        with clients_lock:
            sockets = list(clients)
        for sock in sockets:
            remove_client(sock, announce=False)
        print("[SERVER] Đã dừng.")
