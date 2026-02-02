"""
End-to-end test for collaboration router

Steps:
1. Start a collaborative session (HTTP)
2. Connect to WebSocket
3. Send delta, cursor, chat, ping
4. Print everything received

Requirements:
pip install requests websockets
"""

import asyncio
import json
import requests
import websockets
import struct
import time

API_BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"

JWT_TOKEN = ''
SEGMENTATION_ID = 1
PROJECT_ID = 2


def build_igtl_message(
    data_type="TRANSFORM",
    device_name="TestSegmentation",
    body=b"\x00" * 64
):
    version = 1
    timestamp = int(time.time() * 1e6)  # microseconds
    body_size = len(body)
    crc = 0  # ignore CRC for now

    header = b"".join([
        struct.pack(">H", version),
        data_type.encode("ascii").ljust(12, b"\x00"),
        device_name.encode("ascii").ljust(20, b"\x00"),
        struct.pack(">Q", timestamp),
        struct.pack(">Q", body_size),
        struct.pack(">Q", crc),
    ])

    return header + body



def start_session():
    print("Starting session...")

    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}"
    }

    payload = {
        "project_id": PROJECT_ID,
        "session_name": "Python WS Test"
    }

    r = requests.post(
        f"{API_BASE}/collaboration/sessions",
        json=payload,
        headers=headers,
        timeout=10
    )

    r.raise_for_status()
    data = r.json()

    print("Session started:", data)
    return data["session_id"]


async def websocket_test(session_id: int):
    ws_url = (
        f"{WS_BASE}/collaboration/sessions/"
        f"{session_id}/ws?token={JWT_TOKEN}"
    )

    print("Connecting to WebSocket:", ws_url)

    async with websockets.connect(ws_url) as ws:
        print("WebSocket connected")

        init_msg = await ws.recv()
        print("INIT:", init_msg)

        chat_msg = {
            "type": "chat",
            "message": "Hello from Python test client"
        }
        await ws.send(json.dumps(chat_msg))
        print("Chat sent")

        ping_msg = {"type": "ping"}
        await ws.send(json.dumps(ping_msg))
        print("Ping sent")

        igtl_msg = build_igtl_message(
            data_type="TRANSFORM",
            device_name="Segmentation_1"
        )

        await ws.send(igtl_msg)
        print("OpenIGTLink message sent (binary)")

        print("\nListening for server messages (Ctrl+C to stop)...\n")

        try:
            while True:
                msg = await ws.recv()
                print("RECV:", msg)
        except websockets.ConnectionClosed:
            print("WebSocket closed")


def main():
    # session_id = start_session()
    # time.sleep(0.5)
    session_id=2
    asyncio.run(websocket_test(session_id))


if __name__ == "__main__":
    main()

