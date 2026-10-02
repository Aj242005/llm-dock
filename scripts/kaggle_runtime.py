"""Execute a code file in the user's existing Jupyter kernel without logging its URL.

The runtime URL lives outside the repository in ~/.codex/kaggle-docking-runtime.txt.
No kernel is restarted. Supply --kernel to select a different existing kernel.
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import requests
import websocket

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def execute(base, kernel, code, timeout=120):
    session = requests.Session()
    session.get(base + "/api", timeout=20).raise_for_status()
    url = (
        base.replace("https://", "wss://")
        + f"/api/kernels/{kernel}/channels?session_id={uuid.uuid4().hex}"
    )
    cookies = "; ".join(f"{k}={v}" for k, v in session.cookies.items())
    ws = websocket.create_connection(url, timeout=30, cookie=cookies)
    msg_id = uuid.uuid4().hex
    ws.send(
        json.dumps(
            {
                "header": {
                    "msg_id": msg_id,
                    "username": "docking",
                    "session": uuid.uuid4().hex,
                    "msg_type": "execute_request",
                    "version": "5.3",
                },
                "parent_header": {},
                "metadata": {},
                "channel": "shell",
                "content": {
                    "code": code,
                    "silent": False,
                    "store_history": False,
                    "user_expressions": {},
                    "allow_stdin": False,
                    "stop_on_error": True,
                },
                "buffers": [],
            }
        )
    )
    deadline = time.monotonic() + timeout
    failed = False
    while time.monotonic() < deadline:
        message = json.loads(ws.recv())
        if message.get("parent_header", {}).get("msg_id") != msg_id:
            continue
        content = message["content"]
        kind = message["msg_type"] if "msg_type" in message else message["header"]["msg_type"]
        if kind == "stream":
            print(content["text"], end="", flush=True)
        if kind == "error":
            print(content["ename"], content["evalue"])
            failed = True
        if kind == "status" and content["execution_state"] == "idle":
            ws.close()
            return not failed
    ws.close()
    raise TimeoutError("Kernel execution did not finish within the timeout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code_file", type=Path)
    parser.add_argument("--kernel")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    base = Path.home().joinpath(".codex/kaggle-docking-runtime.txt").read_text().strip()
    kernels = requests.get(base + "/api/kernels", timeout=20).json()
    kernel = args.kernel or kernels[-1]["id"]
    if not execute(base, kernel, args.code_file.read_text(encoding="utf-8"), args.timeout):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
