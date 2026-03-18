"""Test remote-api with device ID headers."""
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
REMOTE_API_URL = "https://homesolutions.systemair.com/gateway/remote-api"


async def try_gql(session, headers, name, query, variables=None):
    payload = {"query": query, "variables": variables or {}}
    async with session.post(
        REMOTE_API_URL, json=payload, headers=headers,
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        body = await resp.text()
        print(f"\n=== {name} (HTTP {resp.status}) ===")
        if len(body) > 5000:
            print(body[:5000] + "... (truncated)")
        else:
            print(body)
        return body


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]
    
    api = SystemairCloudAPI(email=email, password=password)
    
    try:
        await api.login()
        print("Login OK")
        session = api._get_session()
        
        # Try various header combinations for passing device ID
        header_combos = [
            {"x-access-token": api._access_token, "content-type": "application/json",
             "x-device-id": DEVICE_ID, "x-device-type": "LEGACY"},
            {"x-access-token": api._access_token, "content-type": "application/json",
             "deviceId": DEVICE_ID, "deviceType": "LEGACY"},
            {"x-access-token": api._access_token, "content-type": "application/json",
             "device-id": DEVICE_ID, "device-type": "LEGACY"},
            {"x-access-token": api._access_token, "content-type": "application/json",
             "x-deviceid": DEVICE_ID, "x-devicetype": "LEGACY"},
        ]
        
        introspection = '{ __schema { queryType { name } mutationType { name } } }'
        
        for i, headers in enumerate(header_combos):
            extra = {k: v for k, v in headers.items() if k not in ("x-access-token", "content-type")}
            payload = {"query": introspection, "variables": {}}
            async with session.post(
                REMOTE_API_URL, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.text()
                print(f"Headers {extra}: HTTP {resp.status} - {body[:200]}")
                if resp.status == 200:
                    print(f"  FOUND IT! Full response: {body[:1000]}")
                    break
        
        # Also try query param style
        for param_style in [
            f"?deviceId={DEVICE_ID}&deviceType=LEGACY",
            f"?device_id={DEVICE_ID}&device_type=LEGACY",
            f"?deviceId={DEVICE_ID}",
        ]:
            url = REMOTE_API_URL + param_style
            headers = {
                "x-access-token": api._access_token,
                "content-type": "application/json",
            }
            payload = {"query": introspection, "variables": {}}
            async with session.post(
                url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.text()
                print(f"URL {param_style}: HTTP {resp.status} - {body[:200]}")
                if resp.status == 200 and "__schema" in body:
                    print(f"  FOUND IT! Full response: {body[:1000]}")
                    break
        
        # Maybe it's in the JSON payload itself?
        payload_styles = [
            {"query": introspection, "variables": {}, "deviceId": DEVICE_ID, "deviceType": "LEGACY"},
            {"query": introspection, "variables": {}, "extensions": {"deviceId": DEVICE_ID, "deviceType": "LEGACY"}},
        ]
        
        headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
        }
        
        for payload in payload_styles:
            async with session.post(
                REMOTE_API_URL, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.text()
                extra = {k: v for k, v in payload.items() if k not in ("query", "variables")}
                print(f"Payload {extra}: HTTP {resp.status} - {body[:200]}")
                if resp.status == 200 and "__schema" in body:
                    print(f"  FOUND IT! Full response: {body[:1000]}")
                    break
        
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
