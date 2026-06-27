#!/usr/bin/env python3
import asyncio, os, websockets

TCP_HOST = "127.0.0.1"
TCP_PORT = int(os.environ.get("TCP_PORT", 9999))
WS_PORT  = int(os.environ.get("PORT", 8765))

async def bridge(websocket):
    try:
        tcp_reader, tcp_writer = await asyncio.open_connection(TCP_HOST, TCP_PORT)
        async def ws_vers_tcp():
            async for msg in websocket:
                tcp_writer.write((msg + "\n").encode())
                await tcp_writer.drain()
        async def tcp_vers_ws():
            while True:
                ligne = await tcp_reader.readline()
                if not ligne: break
                await websocket.send(ligne.decode("utf-8", errors="replace").strip())
        await asyncio.gather(ws_vers_tcp(), tcp_vers_ws())
    except Exception as e:
        print(f"Bridge erreur: {e}")
    finally:
        try: tcp_writer.close()
        except: pass

async def main():
    print(f"Bridge WS:{WS_PORT} → TCP:{TCP_PORT}")
    async with websockets.serve(bridge, "0.0.0.0", WS_PORT):
        print(f"✅ Bridge actif port {WS_PORT}")
        await asyncio.Future()

asyncio.run(main())
