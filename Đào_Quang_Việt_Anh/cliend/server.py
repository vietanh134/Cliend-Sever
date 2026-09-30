import socket
import threading
import time
import json
import struct
import os
import datetime

HOST = "0.0.0.0"
PORT = 9000

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "received_files")
os.makedirs(SAVE_DIR, exist_ok=True)

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
    sock.sendall(struct.pack("!I", len(h)) + h)
    if payload:
        sock.sendall(payload)

class TCPServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.is_running = False
        self.clients = []
        self.lock = threading.Lock()

    def broadcast_packet(self, header, payload=b"", exclude_sock=None):
        """Send packet to all connected clients except exclude_sock."""
        with self.lock:
            disconnected = []
            for client in self.clients:
                if client == exclude_sock:
                    continue
                try:
                    send_packet(client, header, payload)
                except Exception:
                    disconnected.append(client)
            for d in disconnected:
                if d in self.clients:
                    self.clients.remove(d)

    def start(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.is_running = True
            print(f"[SERVER] TCP Server started on {self.host}:{self.port}")

            while self.is_running:
                try:
                    self.server_socket.settimeout(1.0)
                    client_socket, address = self.server_socket.accept()
                    print(f"[SERVER] New client connected from {address[0]}:{address[1]}")
                    
                    with self.lock:
                        self.clients.append(client_socket)

                    client_thread = threading.Thread(
                        target=self.handle_client, 
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.is_running:
                        print(f"[SERVER ERROR] Accept connection error: {e}")
                    break
        except Exception as e:
            print(f"[SERVER ERROR] Server init failed: {e}")
        finally:
            self.stop()

    def handle_client(self, client_socket, address):
        # Welcome packet in c1.py protocol format
        try:
            welcome_header = {
                "type": "msg",
                "sender": "Server Echo",
                "text": f"Chào mừng {address[0]}:{address[1]}! Server sẵn sàng truyền nhận Tin nhắn & Tập tin."
            }
            send_packet(client_socket, welcome_header)
        except Exception:
            pass

        while self.is_running:
            try:
                try:
                    client_socket.settimeout(1.0)
                    peek_bytes = client_socket.recv(4, socket.MSG_PEEK)
                    if not peek_bytes:
                        print(f"[SERVER] Client {address} disconnected.")
                        break
                except socket.timeout:
                    continue

                try:
                    header, payload = recv_packet(client_socket)
                    msg_type = header.get("type", "msg")

                    if msg_type == "msg":
                        text = header.get("text", "")
                        print(f"[SERVER RECV MSG] From {address}: {text}")
                        
                        reply_text = f"Server đã nhận: '{text}'"
                        if text.upper() == "PING":
                            reply_text = "PONG! (Server is online)"
                        elif text.upper() == "TIME":
                            reply_text = f"Thời gian: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        elif text.upper() == "HELP":
                            reply_text = "Các lệnh thử: PING, TIME, HELP, GET_STATUS"
                        elif text.upper() == "GET_STATUS":
                            reply_text = f"Server Status: Active | Connected Clients: {len(self.clients)}"

                        reply_header = {
                            "type": "msg",
                            "sender": "Server Echo",
                            "text": reply_text
                        }
                        send_packet(client_socket, reply_header)

                    elif msg_type == "file":
                        file_name = header.get("name", "unnamed_file")
                        file_size = header.get("size", len(payload))
                        sender = header.get("sender", f"{address[0]}:{address[1]}")

                        # 1. Save file on Server
                        file_path = os.path.join(SAVE_DIR, os.path.basename(file_name))
                        with open(file_path, "wb") as f:
                            f.write(payload)
                        
                        print(f"[SERVER RECV FILE] From {sender}: {file_name} ({file_size} bytes)")

                        # 2. Echo file packet back to sending client
                        echo_file_header = {
                            "type": "file",
                            "name": file_name,
                            "size": len(payload),
                            "sender": f"Server Echo ({address[0]}:{address[1]})"
                        }
                        send_packet(client_socket, echo_file_header, payload)

                        # 3. Broadcast file packet to all other connected clients
                        broadcast_file_header = {
                            "type": "file",
                            "name": file_name,
                            "size": len(payload),
                            "sender": f"Client {address[0]}:{address[1]}"
                        }
                        self.broadcast_packet(broadcast_file_header, payload, exclude_sock=client_socket)

                except (struct.error, json.JSONDecodeError, ValueError):
                    data = client_socket.recv(1024)
                    if not data:
                        break
                    raw_text = data.decode('utf-8', errors='replace').strip()
                    print(f"[SERVER RECV RAW] From {address}: {raw_text}")
                    response = f"Server đã nhận raw TCP: {raw_text}"
                    client_socket.sendall(response.encode('utf-8'))

            except (ConnectionResetError, BrokenPipeError):
                print(f"[SERVER] Client {address} disconnected abruptly.")
                break
            except Exception as e:
                print(f"[SERVER ERROR] Client {address} error: {e}")
                break

        with self.lock:
            if client_socket in self.clients:
                self.clients.remove(client_socket)
        client_socket.close()

    def stop(self):
        self.is_running = False
        with self.lock:
            for client in self.clients:
                try:
                    client.close()
                except:
                    pass
            self.clients.clear()

        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        print("[SERVER] TCP Server stopped.")

if __name__ == "__main__":
    server = TCPServer()
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
