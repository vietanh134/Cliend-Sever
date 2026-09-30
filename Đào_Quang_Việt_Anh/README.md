# 🚀 Client & Server Pro - Đào Quang Việt Anh (MMT Socket System)

Hệ thống **Client - Server nâng cao** truyền nhận tin nhắn & file dữ liệu thời gian thực dựa trên giao thức TCP Socket và Giao diện Web/Desktop App.

---

## 📌 Thành phần hệ thống

### 1. Server Pro (`server.py`)
- **TCP Socket Server (Cổng 9000)**: Server xử lý bất đồng bộ (`asyncio`) hỗ trợ nhiều Client TCP kết nối song song, nhận/gửi tin nhắn và tập tin dữ liệu (lên tới 100MB).
- **FastAPI Web Server (Cổng 8000)**: Dashboard quản trị trên web tích hợp WebSocket (`/ws`) hiển thị danh sách client kết nối, lịch sử trò chuyện, thống kê và quản lý file lưu trữ trong thư mục `received_files/`.

### 2. Desktop GUI Client (`cliend/c1.py`)
- Giao diện Tkinter Dark Mode hiện đại (Cyan Accent).
- Tự động hiển thị thumbnail ảnh, trích xuất dòng đầu tiên file văn bản (`.txt`, `.py`, `.json`, `.csv`...), tạo link mở file và mở thư mục lưu trữ.
- Tích hợp nút khởi chạy nhanh Web Client Interface.

### 3. Web Client Interface (`cliend/app.py`)
- Backend Flask chạy ở cổng `5000` với Server-Sent Events (SSE).
- Kết nối tới TCP Socket Server và cho phép tương tác trực tiếp qua giao diện trình duyệt web.

---

## ⚡ Hướng dẫn chạy nhanh

### Bước 1: Cài đặt thư viện yêu cầu
```bash
pip install fastapi uvicorn flask pillow
```

### Bước 2: Chạy Server Pro
```bash
python server.py
```
- Web Dashboard sẽ tự động mở tại: `http://localhost:8000`
- TCP Server lắng nghe kết nối tại: `0.0.0.0:9000`

### Bước 3: Chạy Client

#### Option A: Giao diện Desktop GUI (`c1.py`)
```bash
cd cliend
python c1.py
```
*(Hoặc nhấp đúp file `run.bat`)*

#### Option B: Giao diện Web Client (`app.py`)
```bash
cd cliend
python app.py
```
Mở trình duyệt tại địa chỉ: `http://127.0.0.1:5000`

---

## 📡 Giao thức TCP Socket Packet Header

Gói tin TCP được định dạng với **4 bytes Big-Endian Integer** chỉ độ dài Header JSON, tiếp theo là **Header JSON** và **Payload Binary Data**:

```text
[ 4 Bytes Header Length ] + [ JSON Metadata ] + [ Binary Payload (File Data) ]
```

- **Tin nhắn text**:
  ```json
  {"type": "msg", "sender": "Tên_Client", "text": "Nội dung tin nhắn"}
  ```
- **Tập tin binary**:
  ```json
  {"type": "file", "name": "filename.ext", "size": 10240, "sender": "Tên_Client"}
  ```
