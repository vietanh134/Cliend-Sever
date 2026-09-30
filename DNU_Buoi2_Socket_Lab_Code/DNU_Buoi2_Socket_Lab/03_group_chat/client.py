"""Bài 3 - Client phòng chat nhiều người."""

import socket
import threading

PORT = 5002
ENCODING = "utf-8"


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


def receive_messages(client: socket.socket, stop_event: threading.Event) -> None:
    try:
        while not stop_event.is_set():
            message = recv_line(client)
            if message is None:
                print("\n[CLIENT] Server đã đóng kết nối.")
                stop_event.set()
                break
            print(f"\n{message}\nBạn > ", end="", flush=True)
    except OSError:
        if not stop_event.is_set():
            print("\n[CLIENT] Mất kết nối tới server.")
            stop_event.set()


def main() -> None:
    server_ip = input("Nhập IPv4 của server [127.0.0.1]: ").strip() or "127.0.0.1"
    username = input("Nhập tên của bạn: ").strip()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        print(f"[CLIENT] Đang kết nối tới {server_ip}:{PORT} ...")
        client.connect((server_ip, PORT))

        prompt = recv_line(client)
        if prompt != "NAME?":
            print("Protocol không đúng hoặc server không hợp lệ.")
            return

        send_line(client, username)
        result = recv_line(client)
        if result is None:
            print("Server đóng kết nối trước khi hoàn tất đăng nhập.")
            return
        if result.startswith("ERROR|"):
            print(result.split("|", 1)[1])
            return

        print(result.split("|", 1)[1] if "|" in result else result)
        print("Tin nhắn từ các thành viên sẽ xuất hiện ngay khi họ gửi.\n")

        stop_event = threading.Event()
        receive_thread = threading.Thread(
            target=receive_messages,
            args=(client, stop_event),
            daemon=True,
        )
        receive_thread.start()

        try:
            while not stop_event.is_set():
                message = input("Bạn > ").strip()
                if not message:
                    continue
                send_line(client, message)
                if message.lower() == "/quit":
                    stop_event.set()
                    break
        except (EOFError, KeyboardInterrupt):
            try:
                send_line(client, "/quit")
            except OSError:
                pass
            stop_event.set()

        try:
            client.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except ConnectionRefusedError:
        print("Không kết nối được: server chưa chạy, sai IP/cổng, hoặc bị firewall chặn.")
    except OSError as exc:
        print(f"Lỗi mạng: {exc}")
