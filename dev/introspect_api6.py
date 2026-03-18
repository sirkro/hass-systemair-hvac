"""Test device write operations and deeper data retrieval."""
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


async def try_gql(session, api, name, query, variables=None):
    """Try a GraphQL query."""
    headers = {
        "x-access-token": api._access_token,
        "content-type": "application/json",
    }
    payload = {"query": query, "variables": variables or {}}
    async with session.post(
        api._api_url,
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        body = await resp.text()
        print(f"\n=== {name} (HTTP {resp.status}) ===")
        print(body[:2000])
        return body


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]
    
    api = SystemairCloudAPI(email=email, password=password)
    
    try:
        await api.login()
        print("Login OK")
        session = api._get_session()
        
        # ===== Test 1: Try sending WS commands for read/write =====
        ws_url = "wss://homesolutions.systemair.com/streaming/"
        print(f"\n=== WebSocket command tests ===")
        try:
            async with session.ws_connect(
                ws_url,
                protocols=("accessToken", api._access_token),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as ws:
                print("WS connected")
                
                # Try various command formats
                commands = [
                    # Old-style READ command
                    {"type": "READ", "deviceId": DEVICE_ID},
                    # Request device data
                    {"type": "REQUEST_DEVICE_DATA", "deviceId": DEVICE_ID},
                    # Get device view (like old GQL mutation but via WS)
                    {"type": "GET_DEVICE_VIEW", "payload": {"deviceId": DEVICE_ID, "route": "/device/home"}},
                    # Subscribe to device
                    {"type": "SUBSCRIBE", "payload": {"deviceId": DEVICE_ID}},
                    # Subscribe to device updates
                    {"type": "DEVICE_SUBSCRIBE", "payload": {"deviceId": DEVICE_ID}},
                ]
                
                for cmd in commands:
                    await ws.send_json(cmd)
                    print(f"\nSent: {json.dumps(cmd)}")
                    
                    # Wait for response
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=5)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            print(f"  Response: {msg.data[:500]}")
                        else:
                            print(f"  Response type: {msg.type}")
                    except asyncio.TimeoutError:
                        print(f"  (no response)")
                
        except Exception as e:
            print(f"WS Error: {type(e).__name__}: {e}")
        
        # ===== Test 2: Try the reference's GetDeviceView on a different gateway =====
        # The reference uses the same URL, but maybe the mutation name changed
        
        # Let's also introspect to find any hidden device gateway mutations
        # by checking if there's a different entry point at /westcontrol/ path
        headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
        }
        
        # Try /gateway/graphql, /graphql, etc.
        alt_urls = [
            "https://homesolutions.systemair.com/gateway/graphql",
            "https://homesolutions.systemair.com/graphql",
            "https://homesolutions.systemair.com/gateway/device-api",
            "https://homesolutions.systemair.com/device-api",
        ]
        
        introspection = '{ __schema { queryType { fields { name } } mutationType { fields { name } } } }'
        for url in alt_urls:
            try:
                async with session.post(
                    url,
                    json={"query": introspection, "variables": {}},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    body = await resp.text()
                    print(f"\nAlt URL {url}: HTTP {resp.status} ({len(body)} bytes)")
                    if resp.status == 200 and body.startswith("{"):
                        print(body[:1000])
            except Exception as e:
                print(f"Alt URL {url}: {type(e).__name__}: {e}")
        
        # ===== Test 3: Look at the full Broadcast event more carefully =====
        # Maybe we need to connect WS FIRST, then broadcast
        print(f"\n=== Connect WS first, then broadcast ===")
        try:
            async with session.ws_connect(
                ws_url,
                protocols=("accessToken", api._access_token),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as ws:
                print("WS connected, broadcasting...")
                
                # Broadcast
                async with session.post(
                    api._api_url,
                    json={"query": '{ BroadcastDeviceStatuses(deviceIds: ["%s"]) }' % DEVICE_ID, "variables": {}},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    print(f"Broadcast: HTTP {resp.status}")
                
                # Now listen for all messages
                received = 0
                try:
                    while received < 20:
                        msg = await asyncio.wait_for(ws.receive(), timeout=10)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            parsed = json.loads(msg.data)
                            msg_type = parsed.get("type", "unknown")
                            action = parsed.get("action", "")
                            print(f"\n  [{msg_type}:{action}]")
                            print(f"  Full: {msg.data[:2000]}")
                            received += 1
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                            break
                except asyncio.TimeoutError:
                    print(f"\n  (timeout after {received} messages)")
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")
        
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
