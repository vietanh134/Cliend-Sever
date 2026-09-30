import socket
import threading
import time
import json
import struct
import os
import datetime
import uuid
from queue import Queue
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from server import TCPServer

app = Flask(__name__)

# Directory setup for web static uploads
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

IMAGE_EXTS = {".png", ".gif", ".jpg", ".jpeg", ".bmp", ".webp", ".svg"}
TEXT_EXTS = {".txt", ".md", ".py", ".csv", ".log", ".json", ".js", ".html", ".css"}

# System State
state = {
    "host": "172.20.10.4",
    "port": 9000,
    "connected": False,
    "connecting": False,
    "protocol_mode": "auto",
    "last_error": None,
    "stats": {
        "sent_count": 0,
        "recv_count": 0,
        "files_sent": 0,
        "files_recv": 0,
        "bytes_sent": 0,
        "bytes_recv": 0,
        "connected_at": None
    }
}

tcp_socket = None
socket_thread = None
socket_lock = threading.Lock()

messages = []
sse_clients = []
sse_lock = threading.Lock()

local_server = None
local_server_thread = None

# Protocol helper functions
def recv_exact(sock, n, timeout=30.0):
    buf = bytearray()
    start_time = time.time()
    while len(buf) < n:
        try:
            sock.settimeout(2.0)
            chunk = sock.recv(min(65536, n - len(buf)))
            if not chunk:
                raise ConnectionError("Connection closed by peer")
            buf.extend(chunk)
            start_time = time.time()
        except socket.timeout:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Data receive timeout ({timeout}s)")
            continue
    return bytes(buf)

def recv_packet(sock):
    header_len = struct.unpack("!I", recv_exact(sock, 4))[0]
    header = json.loads(recv_exact(sock, header_len).decode('utf-8'))
    size = header.get("size", 0)
    if size > MAX_FILE_SIZE:
        raise ValueError("File size too large (max 100MB)")
    payload = recv_exact(sock, size) if size else b""
    return header, payload

def send_packet(sock, header, payload=b""):
    h = json.dumps(header).encode('utf-8')
    with socket_lock:
        sock.sendall(struct.pack("!I", len(h)) + h)
        if payload:
            sock.sendall(payload)

def broadcast_event(event_type, data):
    payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with sse_lock:
        to_remove = []
        for q in sse_clients:
            try:
                q.put(payload)
            except Exception:
                to_remove.append(q)
        for q in to_remove:
            if q in sse_clients:
                sse_clients.remove(q)

def save_uploaded_file(file_name, data):
    clean_name = os.path.basename(file_name)
    path = os.path.join(UPLOAD_DIR, clean_name)
    base, ext = os.path.splitext(clean_name)
    i = 1
    while os.path.exists(path):
        clean_name = f"{base}_{i}{ext}"
        path = os.path.join(UPLOAD_DIR, clean_name)
        i += 1
    with open(path, "wb") as f:
        f.write(data)
    return clean_name, path

def create_message_obj(msg_type, content, sender="System", extra=None):
    msg_obj = {
        "id": str(uuid.uuid4()),
        "type": msg_type, # 'sent', 'received', 'file', 'system', 'error'
        "content": content,
        "sender": sender,
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
    }
    if extra:
        msg_obj.update(extra)

    messages.append(msg_obj)
    broadcast_event("new_message", msg_obj)
    return msg_obj

def tcp_listener_loop(sock, host, port):
    global tcp_socket
    print(f"[TCP CLIENT] Listening from {host}:{port}...")

    while state["connected"]:
        try:
            try:
                sock.settimeout(1.0)
                peek_bytes = sock.recv(4, socket.MSG_PEEK)
                if not peek_bytes:
                    print("[TCP CLIENT] Server disconnected.")
                    state["connected"] = False
                    state["last_error"] = "Server disconnected."
                    create_message_obj("system", f" Server tại {host}:{port} đã ngắt kết nối.")
                    broadcast_event("status_changed", get_status_data())
                    break
            except socket.timeout:
                continue

            is_c1_packet = False
            try:
                header_len = struct.unpack("!I", peek_bytes)[0]
                if 0 < header_len < 65536:
                    header, payload = recv_packet(sock)
                    is_c1_packet = True
                    
                    state["stats"]["recv_count"] += 1
                    state["stats"]["bytes_recv"] += (4 + header_len + len(payload))

                    mtype = header.get("type", "msg")
                    sender = header.get("sender", f"Server ({host}:{port})")

                    if mtype == "msg":
                        text = header.get("text", "")
                        create_message_obj("received", text, sender)

                    elif mtype == "file":
                        file_name = header.get("name", "received_file")
                        saved_name, full_path = save_uploaded_file(file_name, payload)
                        ext = os.path.splitext(saved_name)[1].lower()

                        file_url = f"/static/uploads/{saved_name}"
                        is_img = ext in IMAGE_EXTS
                        is_txt = ext in TEXT_EXTS

                        preview_text = None
                        if is_txt:
                            try:
                                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                                    preview_text = f.read(1500)
                            except:
                                preview_text = None

                        state["stats"]["files_recv"] += 1

                        file_extra = {
                            "file_name": saved_name,
                            "file_url": file_url,
                            "file_size": len(payload),
                            "is_image": is_img,
                            "is_text": is_txt,
                            "preview_text": preview_text
                        }
                        create_message_obj("file", f"Tập tin từ {sender}: {saved_name}", sender, file_extra)

                    broadcast_event("status_changed", get_status_data())
            except Exception as pe:
                if not is_c1_packet:
                    data = sock.recv(1024)
                    if not data:
                        break
                    state["stats"]["recv_count"] += 1
                    state["stats"]["bytes_recv"] += len(data)

                    text = data.decode('utf-8', errors='replace')
                    create_message_obj("received", text, f"Server ({host}:{port})")
                    broadcast_event("status_changed", get_status_data())

        except socket.timeout:
            continue
        except (ConnectionResetError, ConnectionAbortedError):
            state["connected"] = False
            state["last_error"] = "Mất kết nối tới server."
            create_message_obj("error", f" Mất kết nối tới server {host}:{port}")
            broadcast_event("status_changed", get_status_data())
            break
        except Exception as e:
            if state["connected"]:
                state["connected"] = False
                state["last_error"] = str(e)
                create_message_obj("error", f" Lỗi kết nối: {str(e)}")
                broadcast_event("status_changed", get_status_data())
            break

    with socket_lock:
        if tcp_socket:
            try:
                tcp_socket.close()
            except:
                pass
            tcp_socket = None

def get_status_data():
    return {
        "connected": state["connected"],
        "connecting": state["connecting"],
        "host": state["host"],
        "port": state["port"],
        "protocol_mode": state["protocol_mode"],
        "last_error": state["last_error"],
        "local_server_active": local_server is not None and local_server.is_running,
        "stats": state["stats"]
    }

# Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/static/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(get_status_data())

@app.route("/api/history", methods=["GET"])
def api_history():
    return jsonify(messages)

@app.route("/api/clear", methods=["POST"])
def api_clear():
    messages.clear()
    broadcast_event("cleared", {})
    return jsonify({"status": "ok"})

@app.route("/api/connect", methods=["POST"])
def api_connect():
    global tcp_socket, socket_thread
    req = request.json or {}
    host = req.get("host", "172.20.10.4").strip()
    port = int(req.get("port", 9000))

    if state["connected"]:
        return jsonify({"status": "error", "message": "Đang có kết nối đang hoạt động."}), 400

    state["host"] = host
    state["port"] = port
    state["connecting"] = True
    state["last_error"] = None
    broadcast_event("status_changed", get_status_data())

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        
        with socket_lock:
            tcp_socket = sock
            state["connected"] = True
            state["connecting"] = False
            state["stats"]["connected_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        create_message_obj("system", f" Đã kết nối thành công tới TCP Server {host}:{port}")
        
        socket_thread = threading.Thread(
            target=tcp_listener_loop, 
            args=(sock, host, port),
            daemon=True
        )
        socket_thread.start()

        broadcast_event("status_changed", get_status_data())
        return jsonify({"status": "ok", "message": f"Kết nối thành công {host}:{port}"})
    
    except Exception as e:
        state["connecting"] = False
        state["connected"] = False
        err_msg = f"Không thể kết nối tới {host}:{port} ({str(e)})"
        state["last_error"] = err_msg
        create_message_obj("error", f" {err_msg}")
        broadcast_event("status_changed", get_status_data())
        return jsonify({"status": "error", "message": err_msg}), 500

@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    global tcp_socket
    if state["connected"]:
        state["connected"] = False
        with socket_lock:
            if tcp_socket:
                try:
                    tcp_socket.close()
                except:
                    pass
                tcp_socket = None
        create_message_obj("system", f" Đã ngắt kết nối khỏi {state['host']}:{state['port']}")
        broadcast_event("status_changed", get_status_data())
        return jsonify({"status": "ok", "message": "Đã ngắt kết nối."})
    return jsonify({"status": "ok", "message": "Hiện chưa kết nối."})

@app.route("/api/send", methods=["POST"])
def api_send():
    global tcp_socket
    if not state["connected"] or tcp_socket is None:
        return jsonify({"status": "error", "message": "Chưa kết nối tới TCP Server!"}), 400

    req = request.json or {}
    message = req.get("message", "").strip()
    if not message:
        return jsonify({"status": "error", "message": "Tin nhắn rỗng."}), 400

    try:
        header = {"type": "msg", "sender": "Web Client", "text": message}
        send_packet(tcp_socket, header)
        
        state["stats"]["sent_count"] += 1
        state["stats"]["bytes_sent"] += len(message.encode('utf-8'))
        
        create_message_obj("sent", message, "Bạn (Web Client)")
        broadcast_event("status_changed", get_status_data())
        return jsonify({"status": "ok", "message": "Đã gửi."})
    except Exception as e:
        state["connected"] = False
        state["last_error"] = str(e)
        create_message_obj("error", f" Lỗi gửi tin nhắn: {str(e)}")
        broadcast_event("status_changed", get_status_data())
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/upload_file", methods=["POST"])
def api_upload_file():
    global tcp_socket
    if not state["connected"] or tcp_socket is None:
        return jsonify({"status": "error", "message": "Chưa kết nối tới TCP Server!"}), 400

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Không tìm thấy tập tin đính kèm."}), 400

    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return jsonify({"status": "error", "message": "Tên file không hợp lệ."}), 400

    try:
        file_bytes = uploaded_file.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            return jsonify({"status": "error", "message": "Kích thước file vượt quá 100MB."}), 400

        saved_name, full_path = save_uploaded_file(uploaded_file.filename, file_bytes)

        # Gửi packet file qua TCP socket theo chuẩn c1.py
        header = {
            "type": "file",
            "name": saved_name,
            "size": len(file_bytes),
            "sender": "Web Client"
        }
        send_packet(tcp_socket, header, file_bytes)

        state["stats"]["sent_count"] += 1
        state["stats"]["files_sent"] += 1
        state["stats"]["bytes_sent"] += len(file_bytes)

        ext = os.path.splitext(saved_name)[1].lower()
        file_url = f"/static/uploads/{saved_name}"
        is_img = ext in IMAGE_EXTS
        is_txt = ext in TEXT_EXTS

        preview_text = None
        if is_txt:
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    preview_text = f.read(1500)
            except:
                preview_text = None

        file_extra = {
            "file_name": saved_name,
            "file_url": file_url,
            "file_size": len(file_bytes),
            "is_image": is_img,
            "is_text": is_txt,
            "preview_text": preview_text
        }

        create_message_obj("file", f"Đã gửi tập tin: {saved_name}", "Bạn (Web Client)", file_extra)
        broadcast_event("status_changed", get_status_data())

        return jsonify({"status": "ok", "message": f"Đã gửi thành công tập tin {saved_name}"})
    except Exception as e:
        create_message_obj("error", f" Lỗi khi gửi tập tin: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/server/toggle", methods=["POST"])
def api_server_toggle():
    global local_server, local_server_thread
    if local_server and local_server.is_running:
        local_server.stop()
        local_server = None
        create_message_obj("system", " Đã dừng Local TCP Server trên cổng 9000.")
        broadcast_event("status_changed", get_status_data())
        return jsonify({"status": "ok", "message": "Local Server đã dừng."})
    else:
        try:
            local_server = TCPServer(host="0.0.0.0", port=9000)
            local_server_thread = threading.Thread(target=local_server.start, daemon=True)
            local_server_thread.start()
            time.sleep(0.3)
            create_message_obj("system", " Đã khởi chạy Local TCP Server (hỗ trợ Chat & File c1.py) trên 0.0.0.0:9000!")
            broadcast_event("status_changed", get_status_data())
            return jsonify({"status": "ok", "message": "Local Server đã bật thành công."})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Không thể bật Local Server: {str(e)}"}), 500

@app.route("/api/stream")
def api_stream():
    def event_stream():
        client_queue = Queue()
        with sse_lock:
            sse_clients.append(client_queue)
        
        init_payload = f"event: init\ndata: {json.dumps({'status': get_status_data(), 'history': messages})}\n\n"
        yield init_payload

        try:
            while True:
                msg = client_queue.get(timeout=20)
                yield msg
        except Exception:
            pass
        finally:
            with sse_lock:
                if client_queue in sse_clients:
                    sse_clients.remove(client_queue)

    return Response(event_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    print("[WEB INTERFACE] Web Server running at http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
