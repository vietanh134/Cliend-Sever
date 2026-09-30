DNU - BUỔI 2 - SOCKET LAB
========================

Thư mục:
01_chat_1_1      : Chat TCP giữa 1 client và 1 server - cổng 5000
02_file_transfer : Gửi một tệp từ client sang server - cổng 5001
03_group_chat    : Phòng chat TCP nhiều người - cổng 5002

Chạy trên Windows (PowerShell hoặc Terminal):
1) Kiểm tra Python: py --version
2) Mở terminal trong thư mục bài tương ứng.
3) Chạy server: py server.py
4) Chạy client: py client.py

Thử trên cùng một máy trước bằng 127.0.0.1.
Khi chạy qua LAN/hotspot, client phải nhập IPv4 thật của máy server (xem bằng ipconfig).
Server bind 0.0.0.0 để lắng nghe trên các giao diện mạng; client KHÔNG nhập 0.0.0.0.

Không tắt toàn bộ Windows Firewall. Nếu Windows hỏi quyền cho Python, chỉ cho phép trên Private network dùng cho buổi lab.
