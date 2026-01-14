import random
import socket
import threading
import wx
import string
import secrets


class ControlServer:
    def __init__(self, on_next_callback, on_prev_callback, on_ready_callback, port=0, token=None):

        self.port = port
        self.on_next = on_next_callback
        self.on_prev = on_prev_callback
        self.on_ready = on_ready_callback

        if token:
            self.token = token
        else:
            self.token = self._generate_secure_token()
            print(f"[wxReader ExtCtrl] No token provided. Generated temporary token: {self.token}")

        self._running = False
        self._thread = None
        self._sock = None
        self._lock = threading.Lock()

        self.actual_port = port if port != 0 else None

    @staticmethod
    def _generate_secure_token(length=6):
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        special = "!@#$%^&*()_+"
        all_characters = lowercase + uppercase + string.digits + special

        token_list = [
            secrets.choice(lowercase),
            secrets.choice(uppercase),
            secrets.choice(special)
        ]

        remaining_length = length - 3
        for _ in range(remaining_length):
            token_list.append(secrets.choice(all_characters))

        random.shuffle(token_list)
        return "".join(token_list)

    def get_token(self):
        return self.token

    def start(self):
        with self._lock:
            if self._running:
                return

            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            print(f"[wxReader ExtCtrl] Server starting request...")

    def stop(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
            print(f"[wxReader ExtCtrl] Stop signal sent.")

    def is_running(self):
        return self._running

    def get_port(self):
        return self.actual_port

    def _loop(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except Exception:
            pass

        self._sock.settimeout(1.0)

        try:
            self._sock.bind(('127.0.0.1', self.port))
            self.actual_port = self._sock.getsockname()[1]

            if self.on_ready:
                wx.CallAfter(self.on_ready)

            print(f"[wxReader ExtCtrl] Listening on Port: {self.actual_port} | Token: {self.token}")

            while self._running:
                try:
                    data, _ = self._sock.recvfrom(1024)
                    msg = data.decode('utf-8').strip()

                    if "|" in msg:
                        token_received, cmd = msg.split("|", 1)

                        if token_received == self.token:
                            if cmd == "NEXT":
                                wx.CallAfter(self.on_next)
                            elif cmd == "PREV":
                                wx.CallAfter(self.on_prev)
                        else:
                            print(f"[wxReader ExtCtrl] Invalid Token received: {token_received}")

                except socket.timeout:
                    continue
                except OSError as e:
                    if self._running:
                        print(f"[wxReader ExtCtrl] Socket Error: {e}")
                    break
                except Exception as e:
                    print(f"[wxReader ExtCtrl] Unexpected Error: {e}")

        except OSError as e:
            print(
                f"[wxReader ExtCtrl] CRITICAL: Failed to bind port {self.port}. Is another instance running? Error: {e}")
            self._running = False

        finally:
            if self._sock:
                try:
                    self._sock.close()
                except Exception as e:
                    print(f"[wxReader ExtCtrl] Close error: {e}.")
            self._sock = None
            self.actual_port = None
            print("[wxReader ExtCtrl] Service stopped.")
