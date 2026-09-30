# 🌐 Mạng Máy Tính (MMT) - TCP Socket & Web Client-Server Architecture

Dự án môn học **Mạng Máy Tính (MMT)** triển khai ứng dụng Client - Server truyền nhận dữ liệu thời gian thực (Real-time Messaging & File Transfer) qua giao thức TCP Socket kết hợp giao diện Web Dashboard (FastAPI & WebSocket) và Desktop GUI Client (Tkinter / Flask).

---

## 📋 Mục lục

1. [Giới thiệu tổng quan](#-giới-thiệu-tổng-quan)
2. [Cấu trúc dự án](#-cấu-trúc-dự-án)
3. [Các tính năng nổi bật](#-các-tính-năng-nổi-bật)
4. [Giao thức truyền tải (Custom TCP Protocol Header)](#-giao-thức-truyền-tải-custom-tcp-protocol-header)
5. [Hướng dẫn cài đặt & Khởi chạy](#-hướng-dẫn-cài-đặt--khởi-chạy)
   - [Khởi chạy Máy chủ Server Pro (FastAPI + TCP Server)](#1-máy-chủ-server-pro-fastapi--tcp-server)
   - [Khởi chạy Desktop GUI Client (`c1.py`)](#2-desktop-gui-client-c1py)
   - [Khởi chạy Web Interface Client (`app.py`)](#3-web-interface-client-apppy)
   - [Khởi chạy các bài Lab Socket cơ bản](#4-các-bài-lab-socket-cơ-bản-01-02-03)
6. [Cấu hình mạng & Tường lửa (Firewall)](#-cấu-hình-mạng--tường-lửa-firewall)

---

## 🚀 Giới thiệu tổng quan

Dự án bao gồm 2 phần chính:

1. **`Đào_Quang_Việt_Anh/` - Ứng dụng Client-Server Nâng cao**:
   - **TCP Socket Server (Port 9000)**: Xử lý bất đồng bộ (`asyncio`) hỗ trợ hàng loạt kết nối đồng thời từ các Client, truyền nhận tin nhắn và tập tin lớn (lên tới 100MB).
   - **FastAPI Web Server (Port 8000)**: Giao diện Web quản trị thời gian thực tích hợp WebSocket (`/ws`) và RESTful API để giám sát danh sách client, lịch sử chat và quản lý tập tin lưu trữ.
   - **Desktop GUI Client (`c1.py`)**: Giao diện Tkinter giao diện Dark Mode hiện đại, hỗ trợ xem trước ảnh (Thumbnail), đọc trước file văn bản, mở file/thư mục trực tiếp và mở giao diện Web.
   - **Flask Web Client (`app.py`)**: Client dạng Web điều khiển kết nối TCP Socket qua giao diện trình duyệt web với Server-Sent Events (SSE).

2. **`DNU_Buoi2_Socket_Lab_Code/` - Bộ bài tập Socket Lab cơ bản**:
   - **01_chat_1_1**: Chat TCP 1-1 đơn giản giữa 1 Client và 1 Server (Cổng 5000).
   - **02_file_transfer**: Truyền file từ Client đến Server (Cổng 5001).
   - **03_group_chat**: Phòng chat nhóm đa người dùng dùng luồng (`threading`) qua Socket TCP (Cổng 5002).

---

## 📂 Cấu trúc dự án

```text
MMT/
├── Đào_Quang_Việt_Anh/             # Hệ thống Client - Server chính
│   ├── server.py                   # FastAPI Web Server (Port 8000) & Async TCP Server (Port 9000)
│   ├── received_files/             # Thư mục lưu trữ tập tin tải về của Server
│   └── cliend/                     # Bộ ứng dụng Client
│       ├── c1.py                   # Desktop GUI Client (Tkinter Pro)
│       ├── app.py                  # Web Client Backend (Flask Server-Sent Events)
│       ├── run.bat                 # Script khởi chạy nhanh Client
│       ├── static/                 # CSS/JS và file tải về của Web Client
│       └── templates/              # Giao diện HTML của Web Client
│
├── DNU_Buoi2_Socket_Lab_Code/     # Thư mục bài tập Lab Socket cơ bản
│   └── DNU_Buoi2_Socket_Lab/
│       ├── 01_chat_1_1/            # Lab Chat 1-1 (Port 5000)
│       │   ├── client.py
│       │   └── server.py
│       ├── 02_file_transfer/       # Lab File Transfer (Port 5001)
│       │   ├── client.py
│       │   └── server.py
│       ├── 03_group_chat/          # Lab Group Chat (Port 5002)
│       │   ├── client.py
│       │   └── server.py
│       └── README.txt
└── README.md                       # Tài liệu hướng dẫn sử dụng dự án
```

---

## ✨ Các tính năng nổi bật

- ⚡ **Truyền nhận thời gian thực (Real-time)**: Đồng bộ tin nhắn và tập tin tức thì giữa TCP Socket Clients và Web Browser Clients.
- 📦 **Giao thức đóng gói Struct + JSON**: Tránh trôi gói (sticky packets / framing issue) trên dòng dữ liệu TCP bằng header độ dài 4-byte (`struct.pack("!I", len)`).
- 🖼️ **Xem trước trực quan (Live Preview)**:
  - Tự động phát hiện và hiển thị ảnh thu nhỏ (Thumbnail).
  - Trích xuất nội dung file văn bản (`.txt`, `.py`, `.md`, `.json`, `.csv`,...) để xem trước.
  - Tạo đường dẫn nhấp đúp để mở trực tiếp file hoặc mở thư mục chứa file.
- 🌐 **Web Dashboard Quản trị**: Theo dõi danh sách IP client đang kết nối, số lượng file, dung lượng bộ nhớ, tải file và chat trực tiếp trên trình duyệt.
- 🛡️ **An toàn & Tin cậy**: Tự động xử lý trùng tên file bằng cách gánh số thứ tự (ví dụ: `image_1.png`), giới hạn dung lượng file tối đa (100 MB), tự động dọn dẹp kết nối bị đứt.

---

## 📡 Giao thức truyền tải (Custom TCP Protocol Header)

Mỗi gói tin trao đổi qua TCP Socket có định dạng gồm 3 phần:

```text
+-----------------------+------------------------+-------------------------+
| Header Length (4B)    | JSON Header            | Payload Data (Binary)   |
| Big-Endian Integer    | Meta data (UTF-8)      | (Nội dung file/Tin nhắn)|
+-----------------------+------------------------+-------------------------+
```

1. **4 Bytes đầu (`!I`)**: Chứa số nguyên 32-bit (Big-endian) thể hiện độ dài của `JSON Header`.
2. **JSON Header**: Chứa thông tin mô tả gói tin:
   - Gửi tin nhắn text: `{"type": "msg", "sender": "Client Name", "text": "Nội dung"}`
   - Gửi tập tin: `{"type": "file", "name": "filename.ext", "size": 10240, "sender": "Client Name"}`
3. **Payload Data**: Dữ liệu binary của file (nếu `type` là `"file"`).

---

## 🛠️ Hướng dẫn cài đặt & Khởi chạy

### 📌 Môi trường yêu cầu
- **Python**: Version 3.8 trở lên.
- **Thư viện yêu cầu**:
  ```bash
  pip install fastapi uvicorn flask pillow
  ```

---

### 1. Máy chủ Server Pro (`FastAPI` + `TCP Server`)

Chạy máy chủ chính tích hợp cả TCP Socket Server (Port 9000) và Web Dashboard (Port 8000):

```bash
cd Đào_Quang_Việt_Anh
python server.py
```

- **Giao diện Web Server Dashboard**: `http://localhost:8000` (Tự động mở trình duyệt sau khi chạy).
- **Cổng TCP Socket**: `0.0.0.0:9000` (Lắng nghe toàn bộ giao diện mạng).

---

### 2. Desktop GUI Client (`c1.py`)

Chạy ứng dụng Client giao diện Tkinter trên máy trạm:

```bash
cd Đào_Quang_Việt_Anh/cliend
python c1.py
```
*(Hoặc nhấp đúp file `run.bat` trên Windows)*

- **Nhập IP Server**:
  - Thử nghiệm trên cùng 1 máy: Nhập `127.0.0.1`
  - Thử nghiệm qua mạng LAN / Wi-Fi: Nhập địa chỉ IPv4 của máy Server (VD: `192.168.1.15`).
- **Nhập Port**: `9000`
- Bấm **"Kết nối"** để bắt đầu chat và gửi file!

---

### 3. Web Interface Client (`app.py`)

Chạy Web Client Backend nếu muốn tương tác với TCP Server qua giao diện trình duyệt:

```bash
cd Đào_Quang_Việt_Anh/cliend
python app.py
```

- Mở trình duyệt truy cập: `http://127.0.0.1:5000`
- Bạn có thể kết nối, ngắt kết nối, gửi tin nhắn và upload file qua giao diện Web của Client.

---

### 4. Các bài Lab Socket cơ bản (`01`, `02`, `03`)

Để học tập & chạy thử các ví dụ bài tập lab cơ bản trong thư mục `DNU_Buoi2_Socket_Lab_Code/DNU_Buoi2_Socket_Lab`:

#### 💬 01. Chat TCP 1-1 (Port 5000)
```bash
# Terminal 1 (Server):
cd DNU_Buoi2_Socket_Lab_Code/DNU_Buoi2_Socket_Lab/01_chat_1_1
python server.py

# Terminal 2 (Client):
cd DNU_Buoi2_Socket_Lab_Code/DNU_Buoi2_Socket_Lab/01_chat_1_1
python client.py
```

#### 📁 02. Truyền tập tin TCP (Port 5001)
```bash
# Terminal 1 (Server):
cd DNU_Buoi2_Socket_Lab_Code/DNU_Buoi2_Socket_Lab/02_file_transfer
python server.py

# Terminal 2 (Client):
cd DNU_Buoi2_Socket_Lab_Code/DNU_Buoi2_Socket_Lab/02_file_transfer
python client.py
```

#### 👥 03. Chat Nhóm Multi-Client (Port 5002)
```bash
# Terminal 1 (Server):
cd DNU_Buoi2_Socket_Lab_Code/DNU_Buoi2_Socket_Lab/03_group_chat
python server.py

# Terminal 2 & Terminal 3 (Các Client):
cd DNU_Buoi2_Socket_Lab_Code/DNU_Buoi2_Socket_Lab/03_group_chat
python client.py
```

---

## 🔒 Cấu hình mạng & Tường lửa (Firewall)

1. **Chạy Localhost (Cùng 1 máy)**:
   - Client sử dụng IP `127.0.0.1`.
2. **Chạy qua LAN / Wi-Fi (Khác máy)**:
   - Kiểm tra địa chỉ IPv4 máy Server bằng lệnh `ipconfig` trên Windows Terminal.
   - Client nhập địa chỉ IPv4 vừa tra cứu của Server (Ví dụ: `192.168.1.50`).
   - Server phải bind địa chỉ `0.0.0.0` (Đã được cấu hình mặc định trong `server.py`).
3. **Lưu ý Tường lửa (Windows Firewall)**:
   - Khi chạy Server, nếu Windows hiển thị thông báo tường lửa, tích chọn cho phép ứng dụng Python hoạt động trên mạng **Private Network**.
   - Không nhập `0.0.0.0` ở phía Client.

---

## 👨‍💻 Tác giả

- **Họ và tên**: Đào Quang Việt Anh
- **Môn học**: Mạng Máy Tính (MMT)
- **Cơ sở đào tạo**: Trường Đại Học Đại Nam (DNU)
