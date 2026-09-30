import os
import sys
import json
import struct
import asyncio
import webbrowser
import threading
from datetime import datetime
from urllib.parse import quote, unquote
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Body, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

# ---------- Cấu hình máy chủ ----------
HOST = "0.0.0.0"
TCP_PORT = 9000
WEB_PORT = 8000
MAX_FILE_SIZE = 100 * 1024 * 1024  # Giới hạn tối đa 100 MB mỗi file
SAVE_DIR = "received_files"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_PATH = os.path.join(BASE_DIR, SAVE_DIR)
os.makedirs(SAVE_PATH, exist_ok=True)

INDEX_HTML_PATH = os.path.join(BASE_DIR, "index.html")

# Trạng thái kết nối
tcp_clients = {}  # StreamWriter -> sender_str (ip:port)
active_websockets = set()
message_history = []
history_lock = asyncio.Lock()

# ---------- Tiện ích ----------
def save_file(name: str, data: bytes) -> str:
    """Lưu tệp an toàn vào thư mục received_files, tránh ghi đè."""
    name = os.path.basename(name)
    path = os.path.join(SAVE_PATH, name)
    base, ext = os.path.splitext(name)
    i = 1
    while os.path.exists(path):
        name = f"{base}_{i}{ext}"
        path = os.path.join(SAVE_PATH, name)
        i += 1
    with open(path, "wb") as f:
        f.write(data)
    return name

def init_history_from_saved_dir():
    """Tải trước các tệp đã có trong received_files vào lịch sử hiển thị."""
    if not os.path.exists(SAVE_PATH):
        return
    files = sorted(
        [f for f in os.listdir(SAVE_PATH) if os.path.isfile(os.path.join(SAVE_PATH, f))],
        key=lambda f: os.path.getmtime(os.path.join(SAVE_PATH, f))
    )
    for fname in files:
        fpath = os.path.join(SAVE_PATH, fname)
        mtime = os.path.getmtime(fpath)
        time_str = datetime.fromtimestamp(mtime).strftime("%H:%M:%S")
        message_history.append({
            "type": "file",
            "sender": "Lưu trữ máy chủ",
            "name": fname,
            "size": os.path.getsize(fpath),
            "url": f"/files/{quote(fname)}",
            "time": time_str
        })

init_history_from_saved_dir()

def add_history(item: dict):
    message_history.append(item)
    if len(message_history) > 200:
        message_history.pop(0)

# ---------- WebSocket & Broadcast ----------
async def broadcast_ws(data: dict):
    """Gửi dữ liệu thời gian thực tới tất cả trình duyệt web đang kết nối."""
    msg_json = json.dumps(data, ensure_ascii=False)
    dead_ws = set()
    for ws in list(active_websockets):
        try:
            await ws.send_text(msg_json)
        except Exception:
            dead_ws.add(ws)
    for ws in dead_ws:
        active_websockets.discard(ws)

async def notify_status_change():
    """Cập nhật số lượng và danh sách client TCP tới giao diện web."""
    status_data = {
        "type": "status_update",
        "tcp_clients": len(tcp_clients),
        "tcp_list": list(tcp_clients.values()),
        "total_files": len(os.listdir(SAVE_PATH))
    }
    await broadcast_ws(status_data)

async def broadcast_tcp(header: dict, payload: bytes = b"", exclude: asyncio.StreamWriter = None):
    """Gửi gói tin tới các TCP Client đang kết nối."""
    h = json.dumps(header, ensure_ascii=False).encode("utf-8")
    packet = struct.pack("!I", len(h)) + h + payload
    dead_writers = []
    for writer in list(tcp_clients.keys()):
        if writer is exclude:
            continue
        try:
            writer.write(packet)
            await writer.drain()
        except Exception:
            dead_writers.append(writer)
    for w in dead_writers:
        remove_tcp_client(w)

def remove_tcp_client(writer: asyncio.StreamWriter):
    sender = tcp_clients.pop(writer, None)
    if sender:
        print(f"[-] TCP Client đã ngắt kết nối: {sender}")
        try:
            writer.close()
        except Exception:
            pass

# ---------- Xử lý TCP Client (Socket Server Cổng 9000) ----------
async def handle_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info("peername")
    sender = f"{addr[0]}:{addr[1]}" if addr else "TCP-Client"
    tcp_clients[writer] = sender
    print(f"[+] [TCP Cổng {TCP_PORT}] Kết nối mới từ: {sender}")
    await notify_status_change()

    # Thông báo trên Web UI
    await broadcast_ws({
        "type": "system",
        "text": f"Client TCP {sender} đã kết nối vào máy chủ."
    })

    try:
        while True:
            # Đọc 4 byte độ dài header
            len_bytes = await reader.read(4)
            if not len_bytes:
                break

            is_packet = False
            header = {}
            if len(len_bytes) == 4:
                try:
                    candidate_len = struct.unpack("!I", len_bytes)[0]
                    if 2 <= candidate_len <= 65536:
                        header_json_bytes = await reader.readexactly(candidate_len)
                        header = json.loads(header_json_bytes.decode("utf-8"))
                        if "type" in header:
                            is_packet = True
                except Exception:
                    is_packet = False

            if is_packet:
                size = header.get("size", 0)
                if size > MAX_FILE_SIZE:
                    print(f"[-] File từ {sender} quá lớn ({size} byte), từ chối.")
                    break
                payload = await reader.readexactly(size) if size else b""

                if header["type"] == "msg":
                    text = header.get("text", "")
                    print(f"[{sender}]: {text}")
                    msg_event = {
                        "type": "msg",
                        "sender": sender,
                        "text": text,
                        "time": datetime.now().strftime("%H:%M:%S")
                    }
                    add_history(msg_event)
                    await broadcast_ws(msg_event)
                    await broadcast_tcp({"type": "msg", "sender": sender, "text": text}, exclude=writer)

                elif header["type"] == "file":
                    name = header.get("name", "unknown_file")
                    saved_name = save_file(name, payload)
                    print(f"[{sender}] gửi tệp: {name} ({len(payload)} byte) -> Đã lưu: {saved_name}")
                    file_event = {
                        "type": "file",
                        "sender": sender,
                        "name": saved_name,
                        "size": len(payload),
                        "url": f"/files/{quote(saved_name)}",
                        "time": datetime.now().strftime("%H:%M:%S")
                    }
                    add_history(file_event)
                    # Hiện trực tiếp lên trang web
                    await broadcast_ws(file_event)
                    # Chuyển tiếp cho các TCP client khác
                    await broadcast_tcp(
                        {"type": "file", "sender": sender, "name": saved_name, "size": len(payload)},
                        payload,
                        exclude=writer
                    )
            else:
                # Xử lý client gửi text thô đơn giản
                more = b""
                try:
                    more = await asyncio.wait_for(reader.read(4096), timeout=0.05)
                except asyncio.TimeoutError:
                    pass
                raw_bytes = len_bytes + more
                text = raw_bytes.decode("utf-8", errors="replace").strip()
                if text:
                    print(f"[{sender} (text thô)]: {text}")
                    msg_event = {
                        "type": "msg",
                        "sender": sender,
                        "text": text,
                        "time": datetime.now().strftime("%H:%M:%S")
                    }
                    add_history(msg_event)
                    await broadcast_ws(msg_event)
                    await broadcast_tcp({"type": "msg", "sender": sender, "text": text}, exclude=writer)

    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError, ConnectionError):
        pass
    except Exception as e:
        print(f"[-] Lỗi trong luồng xử lý TCP client {sender}: {e}")
    finally:
        remove_tcp_client(writer)
        await notify_status_change()
        await broadcast_ws({
            "type": "system",
            "text": f"Client TCP {sender} đã ngắt kết nối."
        })

# ---------- Khởi tạo Lifespan & FastAPI ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi động TCP Socket Server
    tcp_server = await asyncio.start_server(handle_tcp_client, HOST, TCP_PORT)
    print("=" * 60)
    print(f"  🚀 MMT Server Pro đang hoạt động:")
    print(f"  👉 Giao diện Web HTML:  http://localhost:{WEB_PORT}")
    print(f"  👉 TCP Socket Server:   {HOST}:{TCP_PORT}")
    print(f"  👉 Thư mục lưu tệp:     {SAVE_PATH}")
    print("=" * 60)

    # Tự động mở trình duyệt sau 0.8 giây
    def open_browser():
        try:
            webbrowser.open(f"http://localhost:{WEB_PORT}")
        except Exception:
            pass
    threading.Timer(0.8, open_browser).start()

    yield

    # Dọn dẹp khi tắt server
    tcp_server.close()
    await tcp_server.wait_closed()
    print("[*] Đã đóng máy chủ TCP.")

app = FastAPI(title="MMT Server", lifespan=lifespan)

# ---------- Endpoints Web HTTP & API ----------
@app.get("/", response_class=HTMLResponse)
async def get_index():
    if os.path.exists(INDEX_HTML_PATH):
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h3>Chưa tìm thấy index.html</h3>", status_code=404)

@app.get("/api/status")
async def get_status():
    total_size = sum(
        os.path.getsize(os.path.join(SAVE_PATH, f))
        for f in os.listdir(SAVE_PATH)
        if os.path.isfile(os.path.join(SAVE_PATH, f))
    )
    return {
        "status": "online",
        "tcp_port": TCP_PORT,
        "web_port": WEB_PORT,
        "tcp_clients": len(tcp_clients),
        "tcp_list": list(tcp_clients.values()),
        "total_files": len(os.listdir(SAVE_PATH)),
        "total_size": total_size
    }

@app.get("/api/history")
async def get_history():
    return message_history

@app.get("/api/files")
async def get_files():
    result = []
    if os.path.exists(SAVE_PATH):
        files = sorted(
            [f for f in os.listdir(SAVE_PATH) if os.path.isfile(os.path.join(SAVE_PATH, f))],
            key=lambda f: os.path.getmtime(os.path.join(SAVE_PATH, f)),
            reverse=True
        )
        for fname in files:
            fpath = os.path.join(SAVE_PATH, fname)
            mtime = os.path.getmtime(fpath)
            result.append({
                "name": fname,
                "size": os.path.getsize(fpath),
                "date": datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M"),
                "ext": os.path.splitext(fname)[1].lower()
            })
    return result

@app.get("/api/file-content/{filename}")
async def get_file_content(filename: str):
    filename = os.path.basename(filename)
    fpath = os.path.join(SAVE_PATH, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="File không tồn tại")
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(50000)  # Đọc tối đa 50KB để xem trước nhanh
        return PlainTextResponse(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files/{filename}")
async def serve_file(filename: str):
    filename = unquote(filename)
    filename = os.path.basename(filename)
    fpath = os.path.join(SAVE_PATH, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="File không tồn tại")
    return FileResponse(fpath, filename=filename)

@app.post("/api/send-msg")
async def api_send_msg(data: dict = Body(...)):
    text = data.get("text", "").strip()
    sender = data.get("sender", "Server")
    if not text:
        return {"status": "empty"}

    msg_event = {
        "type": "msg",
        "sender": sender,
        "text": text,
        "time": datetime.now().strftime("%H:%M:%S")
    }
    add_history(msg_event)
    await broadcast_ws(msg_event)
    await broadcast_tcp({"type": "msg", "sender": sender, "text": text})
    return {"status": "ok"}

@app.post("/api/upload")
async def api_upload(
    file: UploadFile = File(...),
    sender: str = Form("Server"),
    note: str = Form(None)
):
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File vượt quá dung lượng tối đa 100MB")

    saved_name = save_file(file.filename, data)
    file_event = {
        "type": "file",
        "sender": sender,
        "name": saved_name,
        "size": len(data),
        "url": f"/files/{quote(saved_name)}",
        "time": datetime.now().strftime("%H:%M:%S")
    }
    add_history(file_event)

    # 1. Hiển thị trực tiếp tức thì trên giao diện Web
    await broadcast_ws(file_event)

    # 2. Gửi file tới toàn bộ các TCP Client đang kết nối
    await broadcast_tcp(
        {"type": "file", "sender": sender, "name": saved_name, "size": len(data)},
        data
    )

    return {"status": "ok", "file": file_event}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_websockets.add(ws)

    # Gửi cập nhật trạng thái ngay khi client web kết nối
    await ws.send_text(json.dumps({
        "type": "status_update",
        "tcp_clients": len(tcp_clients),
        "tcp_list": list(tcp_clients.values()),
        "total_files": len(os.listdir(SAVE_PATH))
    }))

    try:
        while True:
            text = await ws.receive_text()
            # Xử lý tin nhắn gửi qua WS nếu có
            try:
                msg = json.loads(text)
                if msg.get("type") == "msg":
                    t = msg.get("text", "").strip()
                    if t:
                        event = {
                            "type": "msg",
                            "sender": msg.get("sender", "Web"),
                            "text": t,
                            "time": datetime.now().strftime("%H:%M:%S")
                        }
                        add_history(event)
                        await broadcast_ws(event)
                        await broadcast_tcp({"type": "msg", "sender": msg.get("sender", "Web"), "text": t})
            except Exception:
                pass
    except WebSocketDisconnect:
        active_websockets.discard(ws)
    except Exception:
        active_websockets.discard(ws)

if __name__ == "__main__":
    uvicorn.run("server:app", host=HOST, port=WEB_PORT, reload=False, log_level="info")