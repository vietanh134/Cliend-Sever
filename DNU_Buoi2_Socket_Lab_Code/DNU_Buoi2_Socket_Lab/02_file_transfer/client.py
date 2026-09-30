"""Bài 2 - Client gửi một tệp qua TCP."""

import socket
from pathlib import Path

PORT = 5001
ENCODING = "utf-8"
BUFFER_SIZE = 64 * 1024


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
    file_text = input("Nhập đường dẫn tệp cần gửi: ").strip().strip('"')
    file_path = Path(file_text).expanduser()

    if not file_path.is_file():
        print("Không tìm thấy tệp. Kiểm tra lại đường dẫn.")
        return

    file_size = file_path.stat().st_size
    print(f"[CLIENT] Chuẩn bị gửi: {file_path.name} ({file_size} byte)")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        print(f"[CLIENT] Kết nối tới {server_ip}:{PORT} ...")
        client.connect((server_ip, PORT))

        send_line(client, f"{file_path.name}|{file_size}")

        sent = 0
        with file_path.open("rb") as file_in:
            while True:
                chunk = file_in.read(BUFFER_SIZE)
                if not chunk:
                    break
                client.sendall(chunk)
                sent += len(chunk)

        print(f"[CLIENT] Đã gửi {sent} byte. Chờ server xác nhận...")
        response = recv_line(client)
        print(f"[SERVER] {response or 'Không có phản hồi.'}")


if __name__ == "__main__":
    try:
        main()
    except ConnectionRefusedError:
        print("Không kết nối được: server chưa chạy, sai IP/cổng, hoặc bị firewall chặn.")
    except OSError as exc:
        print(f"Lỗi mạng: {exc}")
