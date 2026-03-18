"""Discover the actual device communication channel."""
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


async def try_ws(session, api):
    """Try connecting to the WebSocket endpoint."""
    ws_url = "wss://homesolutions.systemair.com/streaming/"
    headers = {
        "x-access-token": api._access_token,
    }
    
    try:
        print(f"\n=== Trying WebSocket: {ws_url} ===")
        async with session.ws_connect(
            ws_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as ws:
            print(f"WebSocket connected!")
            
            # Try sending a subscribe message for our device
            subscribe_msg = {
                "type": "subscribe",
                "deviceId": DEVICE_ID,
            }
            await ws.send_json(subscribe_msg)
            print(f"Sent: {json.dumps(subscribe_msg)}")
            
            # Also try the reference format
            subscribe_msg2 = {
                "type": "connection_init",
                "payload": {}
            }
            await ws.send_json(subscribe_msg2)
            print(f"Sent: {json.dumps(subscribe_msg2)}")
            
            # Read messages for a few seconds
            try:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        print(f"Received: {msg.data[:1000]}")
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        print(f"Received binary: {len(msg.data)} bytes")
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"WS Error: {ws.exception()}")
                        break
                    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                        print(f"WS closed: {msg.data}")
                        break
            except asyncio.TimeoutError:
                print("WS read timeout (expected)")
                
    except Exception as e:
        print(f"WebSocket error: {type(e).__name__}: {e}")


async def try_api_paths(session, api):
    """Try various API paths."""
    headers = {
        "x-access-token": api._access_token,
        "content-type": "application/json",
    }
    
    # Paths to try
    paths = [
        f"https://homesolutions.systemair.com/gateway/devices/{DEVICE_ID}",
        f"https://homesolutions.systemair.com/gateway/devices/{DEVICE_ID}/data",
        f"https://homesolutions.systemair.com/gateway/devices/{DEVICE_ID}/registers",
        f"https://homesolutions.systemair.com/gateway/device/{DEVICE_ID}",
        f"https://homesolutions.systemair.com/devices/{DEVICE_ID}",
        f"https://homesolutions.systemair.com/api/devices/{DEVICE_ID}",
        f"https://homesolutions.systemair.com/westcontrol/api",
        f"https://homesolutions.systemair.com/westcontrol/{DEVICE_ID}",
    ]
    
    for path in paths:
        try:
            async with session.get(
                path,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=False,
            ) as resp:
                body = await resp.text()
                status_info = f"HTTP {resp.status}"
                if resp.status in (301, 302, 303, 307, 308):
                    status_info += f" -> {resp.headers.get('Location', 'unknown')}"
                print(f"GET {path}: {status_info} ({len(body)} bytes)")
                if resp.status == 200 and len(body) < 500:
                    print(f"  Body: {body[:500]}")
        except Exception as e:
            print(f"GET {path}: {type(e).__name__}: {e}")
    
    # Try POST to gateway/api with device-specific query patterns
    gql_tests = [
        ("BroadcastDeviceStatuses", """{
          BroadcastDeviceStatuses(deviceIds: ["%s"])
        }""" % DEVICE_ID),
        ("GetDeviceDetails full", """{
          GetDeviceDetails(deviceId: "%s") {
            id
            type
            createdAt
            privateOwners {
              email
              firstName
              lastName
            }
          }
        }""" % DEVICE_ID),
    ]
    
    for name, query in gql_tests:
        async with session.post(
            api._api_url,
            json={"query": query, "variables": {}},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.text()
            print(f"\n=== GQL: {name} (HTTP {resp.status}) ===")
            print(body[:1000])


async def try_ws_with_graphql(session, api):
    """Try GraphQL over WebSocket (subscriptions transport)."""
    ws_url = "wss://homesolutions.systemair.com/streaming/"
    
    # Try with different protocols
    for protocol in [None, "graphql-ws", "graphql-transport-ws"]:
        try:
            kwargs = {
                "headers": {"x-access-token": api._access_token},
                "timeout": aiohttp.ClientTimeout(total=10),
            }
            if protocol:
                kwargs["protocols"] = (protocol,)
            
            print(f"\n=== WS with protocol={protocol} ===")
            async with session.ws_connect(ws_url, **kwargs) as ws:
                print(f"Connected! Protocol: {ws.protocol}")
                
                # Try connection init
                init = {"type": "connection_init", "payload": {"x-access-token": api._access_token}}
                await ws.send_json(init)
                print(f"Sent init")
                
                # Wait for response
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        print(f"Response: {msg.data[:500]}")
                    else:
                        print(f"Response type: {msg.type}, data: {str(msg.data)[:200]}")
                except asyncio.TimeoutError:
                    print("No response (timeout)")
                    
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]
    
    api = SystemairCloudAPI(email=email, password=password)
    
    try:
        await api.login()
        print("Login OK")
        session = api._get_session()
        
        await try_api_paths(session, api)
        await try_ws_with_graphql(session, api)
        # await try_ws(session, api)  # basic WS test
        
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
