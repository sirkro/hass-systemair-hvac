"""Get actual device data via GetView and discover correct register IDs."""
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
        return resp.status, await resp.text()


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
        
        # 1. Introspect return types
        for tn in ["GraphqlProxyView", "GraphqlProxyDeviceStatusOutput", 
                    "ExportOutput", "ActiveAlarmsOutput", "FilterInformationOutput",
                    "DataItemWriteInput", "DataItemImportInput", "RegisterWriteInput",
                    "SerializedDataItemOutputType"]:
            status, body = await gql(session, headers, """
            {
              __type(name: "%s") {
                name kind
                fields {
                  name type { name kind ofType { name kind } }
                }
                inputFields {
                  name type { name kind ofType { name kind } }
                }
              }
            }
            """ % tn)
            data = json.loads(body)
            t = data.get("data", {}).get("__type")
            if t:
                print(f"\n{tn} ({t.get('kind')}):")
                for f in t.get("fields", []) or t.get("inputFields", []):
                    ft = f["type"]
                    type_str = ft.get("name") or f"{ft.get('kind')}({ft.get('ofType', {}).get('name')})"
                    print(f"  {f['name']}: {type_str}")
            else:
                print(f"\n{tn}: NOT FOUND (may be SCALAR)")
        
        # 2. GetDeviceStatus with subfields
        status, body = await gql(session, headers, """
        {
          GetDeviceStatus {
            connectionStatus
          }
        }
        """)
        print(f"\n=== GetDeviceStatus (HTTP {status}) ===")
        print(body[:2000])
        
        # 3. GetView for /device/home
        status, body = await gql(session, headers, """
        query ($input: GetViewInputType!) {
          GetView(input: $input) {
            route
            elements
            dataItems
            title
            translationVariables
          }
        }
        """, variables={"input": {"route": "/device/home"}})
        print(f"\n=== GetView /device/home (HTTP {status}) ===")
        data = json.loads(body)
        if "data" in data and data["data"].get("GetView"):
            view = data["data"]["GetView"]
            print(f"  route: {view.get('route')}")
            print(f"  title: {view.get('title')}")
            print(f"  translationVariables: {str(view.get('translationVariables'))[:200]}")
            
            # dataItems is the key - probably a JSON string with register data
            data_items = view.get("dataItems")
            if isinstance(data_items, str):
                try:
                    parsed_items = json.loads(data_items)
                    print(f"  dataItems (parsed, {len(parsed_items)} items):")
                    for item in parsed_items[:30]:  # first 30
                        print(f"    {item}")
                except:
                    print(f"  dataItems (raw): {data_items[:2000]}")
            else:
                print(f"  dataItems type={type(data_items)}: {str(data_items)[:2000]}")
            
            elements = view.get("elements")
            if isinstance(elements, str):
                try:
                    parsed_elements = json.loads(elements)
                    print(f"  elements ({len(parsed_elements)} items): {str(parsed_elements)[:500]}")
                except:
                    print(f"  elements (raw): {str(elements)[:500]}")
            else:
                print(f"  elements: {str(elements)[:500]}")
        else:
            print(body[:3000])
        
        # 4. Try /device/home/changeMode
        status, body = await gql(session, headers, """
        query ($input: GetViewInputType!) {
          GetView(input: $input) {
            route
            dataItems
          }
        }
        """, variables={"input": {"route": "/device/home/changeMode"}})
        print(f"\n=== GetView /device/home/changeMode (HTTP {status}) ===")
        data = json.loads(body)
        if "data" in data and data["data"].get("GetView"):
            view = data["data"]["GetView"]
            data_items = view.get("dataItems")
            if isinstance(data_items, str):
                try:
                    parsed_items = json.loads(data_items)
                    print(f"  dataItems ({len(parsed_items)} items):")
                    for item in parsed_items[:30]:
                        print(f"    {item}")
                except:
                    print(f"  dataItems: {data_items[:2000]}")
            else:
                print(f"  dataItems: {str(data_items)[:2000]}")
        else:
            print(body[:3000])
        
        # 5. ExportDataItems
        status, body = await gql(session, headers, """
        {
          ExportDataItems {
            version
            type
            registers
          }
        }
        """)
        print(f"\n=== ExportDataItems (HTTP {status}) ===")
        print(body[:5000])
        
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
