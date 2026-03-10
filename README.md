# p2p-editor

Peer-to-peer bidirectional TCP text editor. Both peers listen **and** connect simultaneously — whichever socket establishes first wins.

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
