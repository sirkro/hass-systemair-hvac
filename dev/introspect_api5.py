"""Test WebSocket connection with subprotocol auth and discover device communication."""
import asyncio
import json
import os
import importlib.util

import aiohttp

spec = importlib.util.spec_from_file_location(
    "cloud_api",
    os.path.join(os.path.dirname(__file__), "custom_components", "systemair", "cloud_api.py")
)
cloud_api_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud_api_mod)
SystemairCloudAPI = cloud_api_mod.SystemairCloudAPI

DEVICE_ID = os.environ["SYSTEMAIR_DEVICE_ID"]


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]
    
    api = SystemairCloudAPI(email=email, password=password)
    
    try:
        await api.login()
        print("Login OK")
        session = api._get_session()
        headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
        }
        
        # ===== Test 1: WebSocket with accessToken subprotocol =====
        ws_url = "wss://homesolutions.systemair.com/streaming/"
        print(f"\n=== WebSocket with subprotocol auth ===")
        try:
            async with session.ws_connect(
                ws_url,
                protocols=("accessToken", api._access_token),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as ws:
                print(f"WebSocket connected! Protocol: {ws.protocol}")
                
                # Wait for initial messages
                received = 0
                try:
                    while received < 10:
                        msg = await asyncio.wait_for(ws.receive(), timeout=10)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            print(f"  Received: {msg.data[:500]}")
                            received += 1
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            print(f"  Binary: {len(msg.data)} bytes")
                            received += 1
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                            print(f"  Closed: {msg.data}")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print(f"  Error: {ws.exception()}")
                            break
                except asyncio.TimeoutError:
                    print(f"  (timeout after {received} messages)")
                    
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")
        
        # ===== Test 2: BroadcastDeviceStatuses then listen on WS =====
        print(f"\n=== Broadcast then listen ===")
        
        # First broadcast
        async with session.post(
            api._api_url,
            json={"query": '{ BroadcastDeviceStatuses(deviceIds: ["%s"]) }' % DEVICE_ID, "variables": {}},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.text()
            print(f"  Broadcast: HTTP {resp.status}: {body[:200]}")
        
        # Then connect WS and listen
        try:
            async with session.ws_connect(
                ws_url,
                protocols=("accessToken", api._access_token),
                timeout=aiohttp.ClientTimeout(total=20),
            ) as ws:
                print(f"  WS connected, listening for push events...")
                received = 0
                try:
                    while received < 20:
                        msg = await asyncio.wait_for(ws.receive(), timeout=15)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = msg.data
                            try:
                                parsed = json.loads(data)
                                msg_type = parsed.get("type", "unknown")
                                print(f"  [{msg_type}] {data[:500]}")
                                
                                # If we get a DEVICE_PUSH_EVENT, print the dataItems
                                if msg_type == "DEVICE_PUSH_EVENT":
                                    payload = parsed.get("payload", {})
                                    data_items = payload.get("dataItems", {})
                                    print(f"    dataItems keys: {list(data_items.keys()) if isinstance(data_items, dict) else type(data_items)}")
                            except json.JSONDecodeError:
                                print(f"  (raw) {data[:500]}")
                            received += 1
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                            print(f"  Closed: {msg.data}")
                            break
                except asyncio.TimeoutError:
                    print(f"  (timeout after {received} messages)")
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")
        
        # ===== Test 3: Try WS with token as query param =====
        print(f"\n=== WS with token as query param ===")
        ws_url_with_token = f"wss://homesolutions.systemair.com/streaming/?token={api._access_token}"
        try:
            async with session.ws_connect(
                ws_url_with_token,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as ws:
                print(f"  Connected! Protocol: {ws.protocol}")
                msg = await asyncio.wait_for(ws.receive(), timeout=5)
                print(f"  First message: {msg.type}: {str(msg.data)[:200]}")
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
