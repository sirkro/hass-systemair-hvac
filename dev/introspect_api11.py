"""Full remote-api introspection and device data test."""
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
        timeout=aiohttp.ClientTimeout(total=30),
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
        headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
            "device-id": DEVICE_ID,
            "device-type": "LEGACY",
        }
        
        # 1. Full schema introspection
        await try_gql(session, headers, "Remote API Full Schema", """
        {
          __schema {
            queryType {
              name
              fields { name args { name type { name kind ofType { name kind } } } }
            }
            mutationType {
              name
              fields { name args { name type { name kind ofType { name kind } } } }
            }
          }
        }
        """)
        
        # 2. Introspect GetDeviceViewInput
        await try_gql(session, headers, "GetDeviceViewInput type", """
        {
          __type(name: "GetDeviceViewInput") {
            name kind
            inputFields {
              name
              type { name kind ofType { name kind } }
            }
          }
        }
        """)
        
        # 3. Introspect WriteDeviceValuesInputType
        for tn in ["WriteDeviceValuesInputType", "WriteDeviceValuesInput"]:
            await try_gql(session, headers, f"{tn} type", """
            {
              __type(name: "%s") {
                name kind
                inputFields {
                  name
                  type { name kind ofType { name kind } }
                }
              }
            }
            """ % tn)
        
        # 4. Try GetDeviceView mutation - reference style
        result = await try_gql(session, headers, "GetDeviceView /device/home", """
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
        
        # 5. Also try the /device/home/changeMode route
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
