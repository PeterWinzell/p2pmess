# p2p-editor

Peer-to-peer bidirectional TCP text editor. Both peers listen **and** connect simultaneously — whichever socket establishes first wins.

## License
Apache 2.0 — Copyright (c) 2026 NeuraWin Tech AB.

## Requirements

Python 3.10+ and tkinter. On systems where tkinter isn't bundled:

```bash
# Debian/Ubuntu
sudo apt install python3-tk

# Fedora
sudo dnf install python3-tkinter

# macOS (Homebrew)
brew install python-tk
```

## Install

```bash

#From PyPi
pip install p2pmess --break-system-packages

#pipx
  #Ubuntu
  sudo apt install pipx
  # Mac
  brew install pipx
  pipx ensurepath

pipx install p2pmess

# From source (editable/dev)

pip install -e .

# From a built wheel
pip install dist/p2pmess-0.1.0-py3-none-any.whl

# Directly from GitHub
pip install git+https://github.com/yourorg/p2pmess.git

```

## Build a wheel

```bash
pip install hatchling
python -m hatchling build
```

## Usage

```bash
p2p-editor
```

Configure in the UI:

| Field | Peer A | Peer B |
|-------|--------|--------|
| Local Port | 5001 | 5002 |
| Remote Host | 127.0.0.1 | 127.0.0.1 |
| Remote Port | 5002 | 5001 |

Click **CONNECT** on both peers. Type in the **SEND** pane, transmit with **Ctrl+Enter**.

## Protocol

Newline-delimited JSON over TCP:

```json
{"type": "msg", "text": "hello", "ts": "14:32:01"}
{"type": "ping"}
{"type": "ack"}
```

Keep-alive pings fire every 5 seconds. On disconnect, both sides automatically attempt to reconnect.

## Networking with Tailscale

If the two machines are on different networks or behind VPNs, direct LAN connections won't work. [Tailscale](https://tailscale.com) solves this by creating a private overlay network between your machines.

### Setup

1. Install Tailscale on both machines:
```bash
   brew install tailscale        # macOS
   # or visit https://tailscale.com/download for other platforms
```

2. Start and authenticate (use the same account on both machines):
```bash
   sudo tailscaled &
   sudo tailscale up
```

3. Get each machine's Tailscale IP:
```bash
   tailscale ip
```
   You'll get a `100.x.x.x` address — use these as the Remote Host in p2pmess.

### Notes

- Both machines must be logged into the **same Tailscale account**
- Tailscale works across different networks, VPNs, and firewalls
- Run `tailscale status` to see all connected devices and their IPs