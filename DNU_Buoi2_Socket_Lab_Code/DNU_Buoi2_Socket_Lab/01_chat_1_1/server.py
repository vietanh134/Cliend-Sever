"""Bài 1 - Server chat 1:1 bằng TCP.

Chạy trên máy đóng vai trò server. Server lắng nghe trên mọi IPv4 cục bộ
(0.0.0.0) ở cổng 5000. Client phải kết nối tới IPv4 thật của máy server,
không kết nối tới 0.0.0.0.
"""

import socket

HOST = "0.0.0.0"
PORT = 5000
ENCODING = "utf-8"


def send_line(sock: socket.socket, text: str) -> None:
    """Gửi một thông điệp kết thúc bằng ký tự xuống dòng."""
    sock.sendall((text + "\n").encode(ENCODING))


def recv_line(sock: socket.socket) -> str | None:
    """Nhận đúng một dòng. Trả về None nếu phía bên kia đã đóng kết nối."""
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            return None if not data else data.decode(ENCODING)
        if chunk == b"\n":
            return data.decode(ENCODING).rstrip("\r")
        data.extend(chunk)


def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)

        print(f"[SERVER] Đang lắng nghe tại 0.0.0.0:{PORT}")
        print("[SERVER] Nhấn Ctrl+C để dừng chương trình.\n")

        client_socket, client_address = server.accept()
        with client_socket:
            print(f"[SERVER] Client đã kết nối từ {client_address[0]}:{client_address[1]}")
            send_line(client_socket, "Kết nối thành công. Gõ /quit để thoát.")

            while True:
                message = recv_line(client_socket)
                if message is None:
                    print("[SERVER] Client đã đóng kết nối.")
                    break

                print(f"Client > {message}")

                if message.strip().lower() == "/quit":
                    send_line(client_socket, "Tạm biệt!")
                    print("[SERVER] Kết thúc phiên chat.")
                    break

                reply = input("Server > ").strip()
                if not reply:
                    reply = "(tin nhắn trống)"
                send_line(client_socket, reply)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[SERVER] Đã dừng.")
