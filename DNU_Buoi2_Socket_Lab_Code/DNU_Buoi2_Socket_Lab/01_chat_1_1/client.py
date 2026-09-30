"""Bài 1 - Client chat 1:1 bằng TCP."""

import socket

PORT = 5000
ENCODING = "utf-8"


def send_line(sock: socket.socket, text: str) -> None:
    sock.sendall((text + "\n").encode(ENCODING))


def recv_line(sock: socket.socket) -> str | None:
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            return None if not data else data.decode(ENCODING)
        if chunk == b"\n":
            return data.decode(ENCODING).rstrip("\r")
        data.extend(chunk)


def main() -> None:
    server_ip = input("Nhập IPv4 của server [127.0.0.1]: ").strip() or "127.0.0.1"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        print(f"[CLIENT] Đang kết nối tới {server_ip}:{PORT} ...")
        client.connect((server_ip, PORT))

        welcome = recv_line(client)
        if welcome:
            print(f"[SERVER] {welcome}")

        print(f"[CLIENT] Local endpoint : {client.getsockname()[0]}:{client.getsockname()[1]}")
        print(f"[CLIENT] Remote endpoint: {client.getpeername()[0]}:{client.getpeername()[1]}\n")

        while True:
            message = input("Bạn > ").strip()
            if not message:
                print("Không gửi tin nhắn rỗng.")
                continue

            send_line(client, message)
            response = recv_line(client)
            if response is None:
                print("[CLIENT] Server đã đóng kết nối.")
                break

            print(f"Server > {response}")
            if message.lower() == "/quit":
                break


if __name__ == "__main__":
    try:
        main()
    except ConnectionRefusedError:
        print("Không kết nối được: server chưa chạy, sai IP/cổng, hoặc bị firewall chặn.")
    except OSError as exc:
        print(f"Lỗi mạng: {exc}")
