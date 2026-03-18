"""Find all data item IDs that map to sensor registers."""
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
URL = "https://homesolutions.systemair.com/gateway/remote-api"

# Target Modbus registers (0-indexed) we want to find data item IDs for
TARGETS = {12101, 12102, 12107, 12135, 12400, 12401, 12543, 14000, 14001, 14100, 14101, 14200, 14201}

QUERY = """query ($input: [Int]) { GetDataItems(input: $input) }"""


async def main():
    api = SystemairCloudAPI(email=os.environ["SYSTEMAIR_EMAIL"], password=os.environ["SYSTEMAIR_PASSWORD"])
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

        found = {}
        all_items_by_mb = {}
        
        # Scan ALL possible data item IDs 0-2000
        for start in range(0, 2001, 200):
            ids = list(range(start, start + 200))
            payload = {"query": QUERY, "variables": {"input": ids}}
            async with session.post(URL, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=60)) as resp:
                body = await resp.text()
            data = json.loads(body)
            if data.get("errors"):
                continue
            items = data.get("data", {}).get("GetDataItems")
            if items:
                if isinstance(items, str):
                    items = json.loads(items)
                for item in items:
                    mb = item.get("extension", {}).get("modbusRegister", 0)
                    all_items_by_mb[mb] = item
                    if mb in TARGETS:
                        found[mb] = item

        print(f"\nTotal unique modbus registers returned: {len(all_items_by_mb)}")
        print(f"Found {len(found)}/{len(TARGETS)} target registers:\n")
        
        for mb in sorted(TARGETS):
            if mb in found:
                item = found[mb]
                print(f"  Modbus {mb:>6d} -> ID {item['id']:4d}, value={item.get('value')}, RO={item.get('readOnly')}, dec={item.get('decimals')}")
            else:
                print(f"  Modbus {mb:>6d} -> NOT FOUND")

        # Show all registers in 12000-14999 range we found
        print("\nAll registers in 12000-14999 range:")
        for mb in sorted(all_items_by_mb.keys()):
            if 12000 <= mb <= 14999:
                item = all_items_by_mb[mb]
                print(f"  Modbus {mb:>6d} -> ID {item['id']:4d}, value={item.get('value')}, RO={item.get('readOnly')}, dec={item.get('decimals')}")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
