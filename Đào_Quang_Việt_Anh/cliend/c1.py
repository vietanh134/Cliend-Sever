import socket
import threading
import json
import struct
import os
import sys
import subprocess
import webbrowser
import datetime
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

# Cấu hình mặc định
DEFAULT_SERVER_IP = "172.20.10.4"
DEFAULT_PORT = 9000
MAX_FILE_SIZE = 100 * 1024 * 1024

SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "received_files")
os.makedirs(SAVE_DIR, exist_ok=True)

THUMB = 260
IMAGE_EXTS = {".png", ".gif", ".jpg", ".jpeg", ".bmp", ".webp"}
TEXT_EXTS = {".txt", ".md", ".py", ".csv", ".log", ".json", ".js", ".html"}

client_socket = None
is_connected = False
send_lock = threading.Lock()
image_refs = []
link_count = 0

# ---------- Giao thức Struct + JSON Packet ----------
def recv_exact(sock, n, timeout=30.0):
    buf = bytearray()
    start_time = time.time()
    while len(buf) < n:
        try:
            sock.settimeout(2.0)
            chunk = sock.recv(min(65536, n - len(buf)))
            if not chunk:
                raise ConnectionError("Kết nối đã đóng")
            buf.extend(chunk)
            start_time = time.time()
        except socket.timeout:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Quá thời gian nhận dữ liệu ({timeout}s)")
            continue
    return bytes(buf)

def recv_packet(sock):
    header_len = struct.unpack("!I", recv_exact(sock, 4))[0]
    header = json.loads(recv_exact(sock, header_len).decode('utf-8'))
    size = header.get("size", 0)
    if size > MAX_FILE_SIZE:
        raise ValueError("Tập tin quá lớn (vượt giới hạn 100MB)")
    payload = recv_exact(sock, size) if size else b""
    return header, payload

def send_packet(sock, header, payload=b""):
    h = json.dumps(header).encode('utf-8')
    with send_lock:
        sock.sendall(struct.pack("!I", len(h)) + h)
        if payload:
            sock.sendall(payload)

# ---------- Xử lý Hiển thị Chat & File ----------
def _append(text, tag=None):
    chat_box.config(state="normal")
    if tag:
        chat_box.insert(tk.END, text + "\n", tag)
    else:
        chat_box.insert(tk.END, text + "\n")
    chat_box.config(state="disabled")
    chat_box.see(tk.END)

def log(text, tag=None):
    root.after(0, _append, text, tag)

def update_status_ui(connected, status_msg):
    global is_connected
    is_connected = connected
    if connected:
        lbl_status.config(text=f"● {status_msg}", fg="#10B981")
        btn_connect.config(text="Ngắt kết nối", bg="#EF4444", fg="#FFFFFF")
    else:
        lbl_status.config(text=f"○ {status_msg}", fg="#EF4444")
        btn_connect.config(text="Kết nối", bg="#00C6FF", fg="#000000")

def open_path(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(os.path.abspath(path))
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    except Exception as exc:
        _append(f"Không thể mở: {exc}", "error")

def make_thumbnail(path):
    try:
        if Image:
            img = Image.open(path)
            img.thumbnail((THUMB, THUMB))
            return ImageTk.PhotoImage(img)
        if os.path.splitext(path)[1].lower() in (".png", ".gif"):
            img = tk.PhotoImage(file=path)
            k = max(1, -(-max(img.width(), img.height()) // THUMB))
            return img.subsample(k, k) if k > 1 else img
    except Exception:
        pass
    return None

def read_preview(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read(2000).splitlines()[:8]
        return "\n".join("  │ " + line for line in lines)
    except:
        return ""

def show_file(sender, name, path):
    global link_count
    ext = os.path.splitext(name)[1].lower()
    chat_box.config(state="normal")
    
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    chat_box.insert(tk.END, f"\n[{timestamp}] 📁 {sender} gửi tập tin: {name} ({os.path.getsize(path)} bytes)\n", "file_header")

    if ext in IMAGE_EXTS:
        photo = make_thumbnail(path)
        if photo:
            image_refs.append(photo)
            chat_box.image_create(tk.END, image=photo, padx=8, pady=6)
            chat_box.insert(tk.END, "\n")
    elif ext in TEXT_EXTS:
        chat_box.insert(tk.END, read_preview(path) + "\n", "preview")

    for label, target in (("📂 Mở file", path), ("🗂 Mở thư mục", os.path.dirname(path))):
        link_count += 1
        tag = f"link{link_count}"
        chat_box.insert(tk.END, label, ("link", tag))
        chat_box.tag_bind(tag, "<Button-1>", lambda e, p=target: open_path(p))
        chat_box.insert(tk.END, "   ")
    chat_box.insert(tk.END, "\n")

    chat_box.config(state="disabled")
    chat_box.see(tk.END)

def save_file(name, data):
    name = os.path.basename(name)
    path = os.path.join(SAVE_DIR, name)
    base, ext = os.path.splitext(name)
    i = 1
    while os.path.exists(path):
        path = os.path.join(SAVE_DIR, f"{base}_{i}{ext}")
        i += 1
    with open(path, "wb") as f:
        f.write(data)
    return path

# ---------- Quản lý Luồng Kết nối TCP ----------
def receive_loop(sock):
    while is_connected:
        try:
            header, payload = recv_packet(sock)
            mtype = header.get("type", "msg")
            sender = header.get("sender", "Server")
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")

            if mtype == "msg":
                log(f"[{timestamp}] {sender}: {header.get('text', '')}")
            elif mtype == "file":
                path = save_file(header.get("name", "file"), payload)
                root.after(0, show_file, sender, header.get("name", "file"), path)

        except Exception:
            if is_connected:
                log("⚠️ Mất kết nối tới server.", "error")
                root.after(0, update_status_ui, False, "Đã mất kết nối")
            break

def toggle_connect():
    global client_socket, is_connected
    if is_connected:
        # Ngắt kết nối
        is_connected = False
        if client_socket:
            try:
                client_socket.close()
            except:
                pass
            client_socket = None
        update_status_ui(False, "Đã ngắt kết nối")
        log("🔌 Đã ngắt kết nối khỏi server.", "system")
    else:
        # Thực hiện kết nối
        host = entry_ip.get().strip()
        try:
            port = int(entry_port.get().strip())
        except ValueError:
            messagebox.showerror("Lỗi", "Port phải là số hợp lệ!")
            return

        def do_connect():
            global client_socket, is_connected
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((host, port))
                sock.settimeout(None)

                client_socket = sock
                is_connected = True

                root.after(0, update_status_ui, True, f"Đã kết nối {host}:{port}")
                log(f"⚡ Đã kết nối tới TCP Server {host}:{port}!", "system")

                threading.Thread(target=receive_loop, args=(sock,), daemon=True).start()
            except Exception as e:
                root.after(0, update_status_ui, False, "Kết nối thất bại")
                root.after(0, log, f"❌ Không thể kết nối tới {host}:{port}: {e}", "error")

        threading.Thread(target=do_connect, daemon=True).start()

def send_message():
    if not is_connected or client_socket is None:
        messagebox.showwarning("Cảnh báo", "Bạn chưa kết nối tới server!")
        return
    msg = entry_msg.get().strip()
    if not msg:
        return
    
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    send_packet(client_socket, {"type": "msg", "sender": "Bạn", "text": msg})
    log(f"[{timestamp}] Bạn: {msg}", "sent")
    entry_msg.delete(0, tk.END)

def send_file():
    if not is_connected or client_socket is None:
        messagebox.showwarning("Cảnh báo", "Bạn chưa kết nối tới server!")
        return
    path = filedialog.askopenfilename()
    if not path:
        return
    if os.path.getsize(path) > MAX_FILE_SIZE:
        messagebox.showerror("Lỗi", "Kích thước tập tin vượt quá 100MB!")
        return

    def worker():
        try:
            with open(path, "rb") as f:
                data = f.read()
            name = os.path.basename(path)
            send_packet(client_socket, {"type": "file", "name": name, "size": len(data), "sender": "Bạn"}, data)
            root.after(0, show_file, "Bạn", name, path)
        except Exception as e:
            root.after(0, log, f"❌ Lỗi gửi file: {e}", "error")

    threading.Thread(target=worker, daemon=True).start()

def send_preset(cmd_text):
    if entry_msg:
        entry_msg.delete(0, tk.END)
        entry_msg.insert(0, cmd_text)
        send_message()

def open_web_interface():
    """Khởi chạy backend web (Flask) và mở trình duyệt Web Pro."""
    def run_flask():
        try:
            from app import app
            app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
        except Exception as e:
            print("Web app exception:", e)

    threading.Thread(target=run_flask, daemon=True).start()
    webbrowser.open("http://127.0.0.1:5000")
    log("🌐 Đã mở Giao diện Web Client Pro tại http://127.0.0.1:5000", "system")

# ---------- Giao Diện Tkinter Hiện Đại ----------
root = tk.Tk()
root.title("Client TCP Pro - Chat & Truyền Tập Tin (Hỗ trợ Web Interface)")
root.geometry("620x720")
root.configure(bg="#0B0F19")

# Theme Palette & Style
BG_MAIN = "#0B0F19"
BG_CARD = "#121826"
BG_INPUT = "#1E293B"
TEXT_COLOR = "#F8FAFC"
CYAN_ACCENT = "#00F2FE"

# Header Configuration Bar
header_frame = tk.Frame(root, bg=BG_CARD, padx=12, pady=10)
header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

tk.Label(header_frame, text="Server IP:", bg=BG_CARD, fg=TEXT_COLOR, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, padx=4)
entry_ip = tk.Entry(header_frame, bg=BG_INPUT, fg=TEXT_COLOR, insertbackground=CYAN_ACCENT, width=14, font=("Segoe UI", 9))
entry_ip.insert(0, DEFAULT_SERVER_IP)
entry_ip.grid(row=0, column=1, padx=4)

tk.Label(header_frame, text="Port:", bg=BG_CARD, fg=TEXT_COLOR, font=("Segoe UI", 9, "bold")).grid(row=0, column=2, padx=4)
entry_port = tk.Entry(header_frame, bg=BG_INPUT, fg=TEXT_COLOR, insertbackground=CYAN_ACCENT, width=6, font=("Segoe UI", 9))
entry_port.insert(0, str(DEFAULT_PORT))
entry_port.grid(row=0, column=3, padx=4)

btn_connect = tk.Button(header_frame, text="Kết nối", command=toggle_connect, bg="#00C6FF", fg="#000000", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, px=10)
btn_connect.grid(row=0, column=4, padx=8)

lbl_status = tk.Label(header_frame, text="○ Chưa kết nối", bg=BG_CARD, fg="#EF4444", font=("Segoe UI", 9, "bold"))
lbl_status.grid(row=0, column=5, padx=8)

# Web Interface Launch Button
btn_web = tk.Button(header_frame, text="🌐 Mở Web Interface Pro", command=open_web_interface, bg="#8B5CF6", fg="#FFFFFF", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, px=8)
btn_web.grid(row=0, column=6, padx=8)

# Chat Log Box
chat_box = scrolledtext.ScrolledText(root, state="disabled", wrap=tk.WORD, bg="#0F172A", fg="#F8FAFC", insertbackground=CYAN_ACCENT, font=("Segoe UI", 10))
chat_box.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

# Tag styles
chat_box.tag_config("link", foreground=CYAN_ACCENT, underline=True)
chat_box.tag_config("preview", foreground="#94A3B8", font=("Consolas", 9))
chat_box.tag_config("file_header", foreground="#10B981", font=("Segoe UI", 10, "bold"))
chat_box.tag_config("sent", foreground="#38BDF8")
chat_box.tag_config("system", foreground="#F59E0B", font=("Segoe UI", 9, "italic"))
chat_box.tag_config("error", foreground="#EF4444")
chat_box.tag_bind("link", "<Enter>", lambda e: chat_box.config(cursor="hand2"))
chat_box.tag_bind("link", "<Leave>", lambda e: chat_box.config(cursor=""))

# Quick Presets Bar
preset_frame = tk.Frame(root, bg=BG_MAIN, padx=10)
preset_frame.pack(fill=tk.X, padx=10, pady=2)

tk.Label(preset_frame, text="Thử nhanh:", bg=BG_MAIN, fg="#64748B", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=4)
for cmd in ("PING", "TIME", "GET_STATUS", "HELP"):
    btn_p = tk.Button(preset_frame, text=cmd, command=lambda c=cmd: send_preset(c), bg=BG_INPUT, fg=TEXT_COLOR, font=("Segoe UI", 8), relief=tk.FLAT, px=6)
    btn_p.pack(side=tk.LEFT, padx=3)

# Bottom Input Bar
input_frame = tk.Frame(root, bg=BG_CARD, padx=10, pady=10)
input_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

entry_msg = tk.Entry(input_frame, bg=BG_INPUT, fg=TEXT_COLOR, insertbackground=CYAN_ACCENT, font=("Segoe UI", 10), relief=tk.FLAT)
entry_msg.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 6))
entry_msg.bind("<Return>", lambda event: send_message())

btn_send_file = tk.Button(input_frame, text="📎 Tập tin", command=send_file, bg=BG_INPUT, fg=CYAN_ACCENT, font=("Segoe UI", 9, "bold"), relief=tk.FLAT, px=10)
btn_send_file.pack(side=tk.RIGHT, padx=3)

btn_send_msg = tk.Button(input_frame, text="Gửi", command=send_message, bg=CYAN_ACCENT, fg="#000000", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, px=14)
btn_send_msg.pack(side=tk.RIGHT, padx=3)

log("✨ Đã sẵn sàng. Ấn 'Kết nối' hoặc click '🌐 Mở Web Interface Pro' để dùng trên trình duyệt.", "system")

root.mainloop()