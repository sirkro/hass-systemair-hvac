"""Find the device control/write API endpoint."""
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
        
        # ===== Test 1: Check /westcontrol paths =====
        # The device type says scope=westcontrol_ui, maybe there's a westcontrol API
        paths_get = [
            f"https://homesolutions.systemair.com/westcontrol/api/devices/{DEVICE_ID}",
            f"https://homesolutions.systemair.com/westcontrol/api/v1/devices/{DEVICE_ID}",
            f"https://homesolutions.systemair.com/westcontrol/api/graphql",
            f"https://homesolutions.systemair.com/api/v1/devices/{DEVICE_ID}",
            f"https://homesolutions.systemair.com/api/v1/devices/{DEVICE_ID}/registers",
            f"https://homesolutions.systemair.com/api/v1/devices/{DEVICE_ID}/data",
        ]
        
        for path in paths_get:
            try:
                async with session.get(
                    path, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=False,
                ) as resp:
                    body = await resp.text()
                    if resp.status not in (200, 404, 405):
                        loc = resp.headers.get("Location", "")
                        print(f"GET {path}: HTTP {resp.status} Location={loc}")
                    elif resp.status == 200 and len(body) < 500:
                        print(f"GET {path}: HTTP {resp.status}: {body[:300]}")
                    elif resp.status == 200:
                        print(f"GET {path}: HTTP {resp.status} ({len(body)} bytes) - likely SPA shell")
                    elif resp.status == 404:
                        # Check if the 404 body suggests a different API
                        if len(body) < 300 and "html" not in body.lower():
                            print(f"GET {path}: HTTP 404: {body[:200]}")
                        else:
                            print(f"GET {path}: HTTP 404")
            except Exception as e:
                print(f"GET {path}: {type(e).__name__}: {e}")
        
        # ===== Test 2: Try POST with GQL to westcontrol API paths =====
        gql_urls = [
            "https://homesolutions.systemair.com/westcontrol/api",
            "https://homesolutions.systemair.com/westcontrol/graphql",
        ]
        
        introspection = '{ __schema { queryType { fields { name } } mutationType { fields { name } } } }'
        for url in gql_urls:
            try:
                async with session.post(
                    url,
                    json={"query": introspection, "variables": {}},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    body = await resp.text()
                    print(f"\nPOST {url}: HTTP {resp.status} ({len(body)} bytes)")
                    if resp.status == 200 and body.startswith("{"):
                        print(body[:2000])
                    elif resp.status != 200 and len(body) < 500:
                        print(body[:300])
            except Exception as e:
                print(f"POST {url}: {type(e).__name__}: {e}")
        
        # ===== Test 3: Try device-specific graphql API that the WestControl micro-frontend might use =====
        # Look at the RemoteEntry.js - it might give us the API endpoint
        remote_entry_urls = [
            f"https://homesolutions.systemair.com/westcontrol/remoteEntry.js",
            f"https://homesolutions.systemair.com/westcontrol_ui/remoteEntry.js",
        ]
        
        for url in remote_entry_urls:
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    body = await resp.text()
                    print(f"\nGET {url}: HTTP {resp.status} ({len(body)} bytes)")
                    if resp.status == 200 and len(body) > 100:
                        # Look for API URLs in the JS
                        import re
                        api_urls = re.findall(r'https?://[^\s"\']+(?:api|graphql|gateway|device)[^\s"\']*', body[:50000])
                        if api_urls:
                            print(f"  Found API URLs: {api_urls[:10]}")
                        # Also look for /api/ or /graphql references
                        api_refs = re.findall(r'["\']/(api|graphql|gateway|device|westcontrol)[^"\']*["\']', body[:50000])
                        if api_refs:
                            print(f"  Found path refs: {api_refs[:20]}")
            except Exception as e:
                print(f"GET {url}: {type(e).__name__}: {e}")
        
        # ===== Test 4: Check if there's a device-gateway WS or different streaming path =====
        ws_paths = [
            f"wss://homesolutions.systemair.com/streaming/{DEVICE_ID}",
            f"wss://homesolutions.systemair.com/westcontrol/streaming/",
            f"wss://homesolutions.systemair.com/device-streaming/",
        ]
        
        for ws_path in ws_paths:
            try:
                async with session.ws_connect(
                    ws_path,
                    protocols=("accessToken", api._access_token),
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as ws:
                    print(f"\nWS {ws_path}: Connected!")
                    msg = await asyncio.wait_for(ws.receive(), timeout=3)
                    print(f"  Message: {str(msg.data)[:200]}")
            except Exception as e:
                print(f"WS {ws_path}: {type(e).__name__}: {str(e)[:100]}")
        
        # ===== Test 5: Maybe the write is through the same GraphQL but with a 
        # different mutation name. Check ALL mutations more carefully =====
        # From the schema we saw mutations like UpdateDeviceInfo, AssignDeviceToAccount, etc.
        # Let's check UpdateDeviceInfo input type
        for type_name in ["UpdateDeviceInfoInput", "AssignDeviceToAccountInput"]:
            type_query = """
            {
              __type(name: "%s") {
                name
                kind
                inputFields {
                  name
                  type {
                    name
                    kind
                    ofType { name kind }
                  }
                }
              }
            }
            """ % type_name
            
            async with session.post(
                api._api_url,
                json={"query": type_query, "variables": {}},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.text()
                print(f"\n=== Type: {type_name} (HTTP {resp.status}) ===")
                print(body[:1000])

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
