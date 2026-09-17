#!/usr/bin/env python3

import socket
import struct
import time

HOST = "127.0.0.1"
PORT = 9019

print(f"Toyota AudioSocket test server")
print(f"Listening on {HOST}:{PORT}")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(5)

while True:
    conn, addr = server.accept()

    print()
    print("=" * 70)
    print(f"CONNECTED: {addr}")
    print("=" * 70)

    total_audio = 0
    frames = 0
    start = time.time()

    try:
        while True:
            header = conn.recv(3)

            if not header:
                break

            while len(header) < 3:
                chunk = conn.recv(3 - len(header))
                if not chunk:
                    break
                header += chunk

            if len(header) != 3:
                break

            kind = header[0]
            length = struct.unpack("!H", header[1:3])[0]

            payload = b""

            while len(payload) < length:
                chunk = conn.recv(length - len(payload))
                if not chunk:
                    break
                payload += chunk

            if len(payload) != length:
                break

            frames += 1

            if kind == 0x01:
                total_audio += length

                elapsed = time.time() - start

                if frames % 50 == 0:
                    print(
                        f"Audio frames={frames} "
                        f"bytes={total_audio} "
                        f"time={elapsed:.1f}s"
                    )
            else:
                print(
                    f"AudioSocket packet: "
                    f"type=0x{kind:02x} length={length}"
                )

    except Exception as e:
        print(f"Connection error: {e}")

    finally:
        print(
            f"DISCONNECTED | frames={frames} "
            f"audio_bytes={total_audio}"
        )
        conn.close()
