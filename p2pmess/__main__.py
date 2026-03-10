#!/usr/bin/env python3
"""
p2p_editor.__main__ — Peer-to-peer bidirectional TCP text editor
Both peers listen AND connect; first established socket wins.
Protocol: newline-delimited JSON  {"type": "msg"|"ack"|"ping", "text": str, "ts": str}
"""

import json
import socket
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────────
# Protocol helpers
# ──────────────────────────────────────────────────────────────────────────────

def encode(payload: dict) -> bytes:
    return (json.dumps(payload) + "\n").encode()

def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ──────────────────────────────────────────────────────────────────────────────
# Network layer — symmetric P2P
# ──────────────────────────────────────────────────────────────────────────────

class P2PLink:
    """
    Maintains exactly one active TCP connection between two peers.
    Both sides simultaneously:
      • listen on local_port  (server role)
      • try to connect to remote_host:remote_port  (client role)
    Whichever socket connects first wins; the other attempt is discarded.
    """

    PING_INTERVAL = 5   # seconds between keep-alive pings
    RECONNECT_DELAY = 2

    def __init__(self, local_port: int, remote_host: str, remote_port: int,
                 on_message, on_status):
        self.local_port   = local_port
        self.remote_host  = remote_host
        self.remote_port  = remote_port
        self.on_message   = on_message   # callback(text: str)
        self.on_status    = on_status    # callback(status: str, connected: bool)

        self._sock        = None
        self._lock        = threading.Lock()
        self._running     = True

        threading.Thread(target=self._server_loop, daemon=True).start()
        threading.Thread(target=self._client_loop, daemon=True).start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _adopt(self, sock: socket.socket, role: str) -> bool:
        """Try to become the owner of sock; returns True if accepted."""
        with self._lock:
            if self._sock is not None:
                sock.close()
                return False
            self._sock = sock
        peer = sock.getpeername()
        self.on_status(f"Connected ({role}) ← {peer[0]}:{peer[1]}", True)
        threading.Thread(target=self._reader, args=(sock,), daemon=True).start()
        threading.Thread(target=self._pinger, args=(sock,), daemon=True).start()
        return True

    def _discard(self, sock: socket.socket):
        with self._lock:
            if self._sock is sock:
                self._sock = None
        try:
            sock.close()
        except OSError:
            pass
        self.on_status("Disconnected — reconnecting…", False)

    def _reader(self, sock: socket.socket):
        buf = b""
        while self._running:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._dispatch(line)
            except OSError:
                break
        self._discard(sock)

    def _dispatch(self, line: bytes):
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return
        if msg.get("type") == "msg":
            self.on_message(msg.get("text", ""), msg.get("ts", ""))
        # ping/ack are silently consumed

    def _pinger(self, sock: socket.socket):
        while self._running:
            time.sleep(self.PING_INTERVAL)
            try:
                with self._lock:
                    if self._sock is not sock:
                        break
                sock.sendall(encode({"type": "ping"}))
            except OSError:
                break

    # ── Server loop ───────────────────────────────────────────────────────────

    def _server_loop(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("", self.local_port))
            srv.listen(1)
        except OSError as e:
            self.on_status(f"Cannot bind :{self.local_port} — {e}", False)
            return
        self.on_status(f"Listening on :{self.local_port}", False)
        while self._running:
            srv.settimeout(1.0)
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._adopt(conn, "server")
        srv.close()

    # ── Client loop ───────────────────────────────────────────────────────────

    def _client_loop(self):
        while self._running:
            with self._lock:
                already = self._sock is not None
            if already:
                time.sleep(self.RECONNECT_DELAY)
                continue
            try:
                s = socket.create_connection(
                    (self.remote_host, self.remote_port), timeout=3
                )
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._adopt(s, "client")
            except (OSError, socket.timeout):
                pass
            time.sleep(self.RECONNECT_DELAY)

    # ── Public API ────────────────────────────────────────────────────────────

    def send(self, text: str) -> bool:
        with self._lock:
            sock = self._sock
        if sock is None:
            return False
        try:
            sock.sendall(encode({"type": "msg", "text": text, "ts": ts()}))
            return True
        except OSError:
            self._discard(sock)
            return False

    def connected(self) -> bool:
        with self._lock:
            return self._sock is not None

    def close(self):
        self._running = False
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except OSError:
                    pass


# ──────────────────────────────────────────────────────────────────────────────
# GUI
# ──────────────────────────────────────────────────────────────────────────────

BG      = "#0d1117"
BG2     = "#161b22"
BG3     = "#21262d"
BORDER  = "#30363d"
FG      = "#e6edf3"
FG_DIM  = "#8b949e"
GREEN   = "#3fb950"
RED     = "#f85149"
AMBER   = "#d29922"
BLUE    = "#58a6ff"
CURSOR  = "#58a6ff"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("P2P Editor")
        self.configure(bg=BG)
        self.minsize(700, 600)
        self.protocol("WM_DELETE_WINDOW", self._quit)

        self._link: P2PLink | None = None
        self._build_ui()
        self._apply_geometry()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _apply_geometry(self):
        w, h = 820, 680
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        mono = tkfont.Font(family="JetBrains Mono", size=11)
        if mono.actual("family") not in ("JetBrains Mono",):
            mono = tkfont.Font(family="Courier New", size=11)
        ui = tkfont.Font(family="Segoe UI", size=10)

        # ── Top bar: connection config ─────────────────────────────────────
        bar = tk.Frame(self, bg=BG2, pady=8, padx=12)
        bar.pack(fill="x")

        def lbl(parent, text, **kw):
            return tk.Label(parent, text=text, bg=BG2, fg=FG_DIM,
                            font=ui, **kw)

        lbl(bar, "LOCAL PORT").pack(side="left")
        self._local_port = self._entry(bar, ui, "5001", width=6)
        self._local_port.pack(side="left", padx=(4, 14))

        lbl(bar, "REMOTE HOST").pack(side="left")
        self._remote_host = self._entry(bar, ui, "127.0.0.1", width=13)
        self._remote_host.pack(side="left", padx=(4, 4))

        lbl(bar, ":").pack(side="left")
        self._remote_port = self._entry(bar, ui, "5002", width=6)
        self._remote_port.pack(side="left", padx=(4, 14))

        self._connect_btn = tk.Button(
            bar, text="CONNECT", font=ui, bg=BG3, fg=GREEN,
            activebackground=BG3, activeforeground=GREEN,
            relief="flat", bd=0, padx=10, pady=4,
            cursor="hand2", command=self._toggle_connect
        )
        self._connect_btn.pack(side="left")

        # status dot + text on right
        self._dot = tk.Label(bar, text="●", fg=RED, bg=BG2, font=ui)
        self._dot.pack(side="right", padx=(0, 4))
        self._status_var = tk.StringVar(value="Disconnected")
        tk.Label(bar, textvariable=self._status_var, bg=BG2,
                 fg=FG_DIM, font=ui).pack(side="right", padx=(0, 6))

        # ── Main pane ──────────────────────────────────────────────────────
        pane = tk.PanedWindow(self, orient="vertical", bg=BORDER,
                              sashrelief="flat", sashwidth=4)
        pane.pack(fill="both", expand=True, padx=0, pady=0)

        # SEND pane
        send_frame = self._pane_frame(pane, "SEND  (Ctrl+Enter to transmit)")
        self._send_text = self._editor(send_frame, mono, editable=True)
        pane.add(send_frame, minsize=120)

        # RECEIVE pane
        recv_frame = self._pane_frame(pane, "RECEIVED")
        self._recv_text = self._editor(recv_frame, mono, editable=False)
        pane.add(recv_frame, minsize=120)

        # ── Bottom status bar ──────────────────────────────────────────────
        sbar = tk.Frame(self, bg=BG3, pady=3, padx=12)
        sbar.pack(fill="x", side="bottom")
        self._info_var = tk.StringVar(value="Not connected — configure and click CONNECT")
        tk.Label(sbar, textvariable=self._info_var, bg=BG3,
                 fg=FG_DIM, font=tkfont.Font(family="Segoe UI", size=9)
                 ).pack(side="left")

        # Key bindings
        self._send_text.bind("<Control-Return>", self._send)
        self._send_text.bind("<Control-KP_Enter>", self._send)

    def _pane_frame(self, parent, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=BG)
        hdr = tk.Frame(outer, bg=BG2, pady=4, padx=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text=title, bg=BG2, fg=FG_DIM,
                 font=tkfont.Font(family="Segoe UI", size=9, weight="bold")
                 ).pack(side="left")
        return outer

    def _editor(self, parent: tk.Frame, mono, editable: bool) -> tk.Text:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(frame, bg=BG2, troughcolor=BG2,
                          activebackground=BORDER, width=10)
        sb.pack(side="right", fill="y")

        t = tk.Text(
            frame,
            font=mono, bg=BG, fg=FG,
            insertbackground=CURSOR,
            selectbackground=BG3, selectforeground=FG,
            relief="flat", bd=0,
            padx=12, pady=10,
            wrap="word",
            yscrollcommand=sb.set,
            state="normal" if editable else "disabled",
            cursor="xterm" if editable else "arrow",
            spacing3=2,
        )
        t.pack(side="left", fill="both", expand=True)
        sb.config(command=t.yview)
        return t

    def _entry(self, parent, font, default="", **kw) -> tk.Entry:
        e = tk.Entry(parent, font=font, bg=BG3, fg=FG,
                     insertbackground=CURSOR, relief="flat",
                     highlightthickness=1, highlightcolor=BLUE,
                     highlightbackground=BORDER, **kw)
        e.insert(0, default)
        return e

    # ── Connection ────────────────────────────────────────────────────────────

    def _toggle_connect(self):
        if self._link is not None:
            self._link.close()
            self._link = None
            self._connect_btn.config(text="CONNECT", fg=GREEN)
            self._set_status("Disconnected", False)
            return

        try:
            lp = int(self._local_port.get())
            rp = int(self._remote_port.get())
            rh = self._remote_host.get().strip()
        except ValueError:
            self._set_status("Invalid port number", False)
            return

        self._link = P2PLink(lp, rh, rp,
                             on_message=self._on_message,
                             on_status=self._on_status)
        self._connect_btn.config(text="DISCONNECT", fg=RED)

    # ── Callbacks (arrive from worker threads) ────────────────────────────────

    def _on_status(self, msg: str, connected: bool):
        self.after(0, self._set_status, msg, connected)

    def _on_message(self, text: str, timestamp: str):
        self.after(0, self._append_received, text, timestamp)

    # ── UI updates (always on main thread via after()) ────────────────────────

    def _set_status(self, msg: str, connected: bool):
        self._status_var.set(msg)
        self._dot.config(fg=GREEN if connected else RED)
        self._info_var.set(msg)

    def _append_received(self, text: str, timestamp: str):
        self._recv_text.config(state="normal")
        if self._recv_text.index("end-1c") != "1.0":
            self._recv_text.insert("end", "\n\n")
        self._recv_text.insert("end", f"[{timestamp}]\n", "ts")
        self._recv_text.insert("end", text)
        self._recv_text.tag_config("ts", foreground=FG_DIM)
        self._recv_text.see("end")
        self._recv_text.config(state="disabled")

    # ── Send ──────────────────────────────────────────────────────────────────

    def _send(self, event=None):
        if self._link is None or not self._link.connected():
            self._info_var.set("⚠  Not connected")
            return "break"
        text = self._send_text.get("1.0", "end-1c").strip()
        if not text:
            return "break"
        if self._link.send(text):
            self._send_text.config(fg=FG_DIM)
            self.after(300, lambda: self._send_text.config(fg=FG))
            self._info_var.set(f"Sent at {ts()}")
        else:
            self._info_var.set("⚠  Send failed — connection lost?")
        return "break"

    def _quit(self):
        if self._link:
            self._link.close()
        self.destroy()


# ──────────────────────────────────────────────────────────────────────────────

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
