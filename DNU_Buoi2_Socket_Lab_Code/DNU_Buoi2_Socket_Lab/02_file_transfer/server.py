"""Bài 2 - Server nhận một tệp qua TCP.

Application protocol rất nhỏ:
1) Client gửi một dòng: <ten_file>|<so_byte>\n
2) Client gửi đúng <so_byte> byte dữ liệu.
3) Server trả một dòng xác nhận OK|... hoặc ERROR|...
"""

import socket
from pathlib import Path

HOST = "0.0.0.0"
PORT = 5001
ENCODING = "utf-8"
BUFFER_SIZE = 64 * 1024
SAVE_DIR = Path(__file__).resolve().parent / "received_files"


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
    raise ValueError("Header quá dài.")


def recv_exact_to_file(sock: socket.socket, output_path: Path, size: int) -> int:
    remaining = size
    received = 0
    with output_path.open("wb") as file_out:
        while remaining > 0:
            chunk = sock.recv(min(BUFFER_SIZE, remaining))
            if not chunk:
                raise ConnectionError("Client đóng kết nối trước khi gửi đủ dữ liệu.")
            file_out.write(chunk)
            received += len(chunk)
            remaining -= len(chunk)
    return received


def choose_output_path(filename: str) -> Path:
    safe_name = Path(filename).name
    if not safe_name:
        raise ValueError("Tên tệp không hợp lệ.")

    output = SAVE_DIR / safe_name
    if not output.exists():
        return output

    stem = output.stem
    suffix = output.suffix
    counter = 1
    while True:
        candidate = SAVE_DIR / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def handle_client(client_socket: socket.socket, client_address: tuple[str, int]) -> None:
    header = recv_line(client_socket)
    if header is None:
        raise ConnectionError("Không nhận được header.")

    try:
        filename, size_text = header.rsplit("|", 1)
        size = int(size_text)
        if size < 0:
            raise ValueError
    except ValueError as exc:
        raise ValueError("Header phải có dạng <ten_file>|<so_byte>.") from exc

    output_path = choose_output_path(filename)
    print(f"[SERVER] Nhận '{filename}' ({size} byte) từ {client_address[0]}:{client_address[1]}")

    received = recv_exact_to_file(client_socket, output_path, size)
    print(f"[SERVER] Đã lưu: {output_path.name} ({received} byte)")
    send_line(client_socket, f"OK|{output_path.name}|{received}")


def main() -> None:
    SAVE_DIR.mkdir(exist_ok=True)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(5)

        print(f"[SERVER] File server đang lắng nghe tại 0.0.0.0:{PORT}")
        print(f"[SERVER] Tệp nhận được sẽ lưu tại: {SAVE_DIR}")
        print("[SERVER] Nhấn Ctrl+C để dừng.\n")

        while True:
            client_socket, client_address = server.accept()
            with client_socket:
                try:
                    handle_client(client_socket, client_address)
                except Exception as exc:
                    print(f"[SERVER] Lỗi: {exc}")
                    try:
                        send_line(client_socket, f"ERROR|{exc}")
                    except OSError:
                        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[SERVER] Đã dừng.")
