"""Test the remote-api endpoint for device control."""
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


async def try_gql(session, headers, name, query, variables=None, url=REMOTE_API_URL):
    payload = {"query": query, "variables": variables or {}}
    async with session.post(
        url, json=payload, headers=headers,
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        body = await resp.text()
        print(f"\n=== {name} (HTTP {resp.status}) ===")
        if len(body) > 3000:
            print(body[:3000] + "... (truncated)")
        else:
            print(body)
        return body


async def introspect_type(session, headers, type_name, url=REMOTE_API_URL):
    query = """
    {
      __type(name: "%s") {
        name
        kind
        fields {
          name
          type { name kind ofType { name kind ofType { name kind } } }
        }
        inputFields {
          name
          type { name kind ofType { name kind } }
        }
      }
    }
    """ % type_name
    
    async with session.post(
        url, json={"query": query, "variables": {}}, headers=headers,
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        body = await resp.text()
        if resp.status == 200 and body.startswith("{"):
            return json.loads(body)
        return {"error": f"HTTP {resp.status}: {body[:300]}"}


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
        
        # 1. Introspect the remote-api schema
        await try_gql(session, headers, "Remote API Schema", """
        {
          __schema {
            queryType { name fields { name } }
            mutationType { name fields { name } }
          }
        }
        """)
        
        # 2. Introspect key types on remote-api
        for type_name in ["GetDeviceViewInput", "WriteDeviceValuesInputType", 
                          "WriteDeviceValuesInput", "DeviceViewResult", "GetDeviceViewResult"]:
            r = await introspect_type(session, headers, type_name)
            print(f"\n--- Type: {type_name} ---")
            print(json.dumps(r, indent=2))
        
        # 3. Try GetDeviceView mutation (reference style)
        await try_gql(session, headers, "GetDeviceView /device/home", """
            mutation ($input: GetDeviceViewInput!) {
              GetDeviceView(input: $input) {
                route
                elements
                dataItems
                title
                translationVariables
              }
            }
        """, variables={"input": {"deviceId": DEVICE_ID, "route": "/device/home"}})
        
        # 4. Try GetDeviceView for changeMode route
        await try_gql(session, headers, "GetDeviceView /device/home/changeMode", """
            mutation ($input: GetDeviceViewInput!) {
              GetDeviceView(input: $input) {
                route
                elements
                dataItems
                title
                translationVariables
              }
            }
        """, variables={"input": {"deviceId": DEVICE_ID, "route": "/device/home/changeMode"}})
        
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
