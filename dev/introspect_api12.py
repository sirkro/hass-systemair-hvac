"""Test actual remote-api operations: GetView, GetDataItems, WriteDataItems."""
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


async def gql(session, headers, query, variables=None):
    payload = {"query": query, "variables": variables or {}}
    async with session.post(
        REMOTE_API_URL, json=payload, headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        body = await resp.text()
        return resp.status, body


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
        
        # 1. Introspect all relevant types
        types_to_check = [
            "GetViewInputType", "WriteDataItemsInput", "GraphqlProxyImportInput",
            "GraphqlProxyImportRegistersInput", "UnitMonitoringDataItemsInput",
            "VerifyPasswordProtectionInput",
        ]
        
        for tn in types_to_check:
            status, body = await gql(session, headers, """
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
            data = json.loads(body)
            t = data.get("data", {}).get("__type")
            if t:
                print(f"\n{tn}:")
                for f in t.get("inputFields", []):
                    ft = f["type"]
                    type_str = ft.get("name") or f"{ft.get('kind')}({ft.get('ofType', {}).get('name')})"
                    print(f"  {f['name']}: {type_str}")
            else:
                print(f"\n{tn}: NOT FOUND")
        
        # 2. GetDeviceStatus (no args)
        status, body = await gql(session, headers, "{ GetDeviceStatus }")
        print(f"\n=== GetDeviceStatus (HTTP {status}) ===")
        print(body[:2000])
        
        # 3. GetView - need to know the input type first
        # Let's also check what GetView returns
        status, body = await gql(session, headers, """
        {
          __type(name: "RootQueryType") {
            fields {
              name
              type {
                name kind
                ofType { name kind fields { name type { name kind } } }
              }
            }
          }
        }
        """)
        print(f"\n=== RootQueryType field types (HTTP {status}) ===")
        print(body[:3000])
        
        # 4. Try GetView with a route
        status, body = await gql(session, headers, """
        query ($input: GetViewInputType!) {
          GetView(input: $input)
        }
        """, variables={"input": {"route": "/device/home"}})
        print(f"\n=== GetView /device/home (HTTP {status}) ===")
        print(body[:3000])
        
        # 5. Try GetDataItems - with some known register IDs from the reference
        # REG_TC_SP=2000, REG_USERMODE_MODE=1160, REG_SENSOR_OAT=12101
        status, body = await gql(session, headers, """
        query ($input: [Int]) {
          GetDataItems(input: $input)
        }
        """, variables={"input": [2000, 1160, 12101, 2504]})
        print(f"\n=== GetDataItems (HTTP {status}) ===")
        print(body[:3000])
        
        # 6. Try GetDataItems with no args (get all?)
        status, body = await gql(session, headers, "{ GetDataItems }")
        print(f"\n=== GetDataItems (no args) (HTTP {status}) ===")
        print(body[:3000])
        
        # 7. ExportDataItems
        status, body = await gql(session, headers, "{ ExportDataItems }")
        print(f"\n=== ExportDataItems (HTTP {status}) ===")
        print(body[:3000])
        
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
