"""Find ALL valid data item IDs by probing in small batches, then find sensor registers."""
import asyncio
import json
import os
import importlib.util
import aiohttp

spec = importlib.util.spec_from_file_location(
    "cloud_api",
    "custom_components/systemair/cloud_api.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

URL = "https://homesolutions.systemair.com/gateway/remote-api"
QUERY = """query ($input: [Int]) { GetDataItems(input: $input) }"""

TARGETS = {12101, 12102, 12107, 12135, 12400, 12401, 12543, 14000, 14001, 14100, 14101, 14200, 14201}


async def try_ids(session, headers, ids):
    """Try a batch of IDs. Returns items or None on error."""
    payload = {"query": QUERY, "variables": {"input": ids}}
    async with session.post(URL, json=payload, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=30)) as resp:
        data = json.loads(await resp.text())
    if data.get("errors"):
        return None
    items = data.get("data", {}).get("GetDataItems")
    if isinstance(items, str):
        items = json.loads(items)
    return items


async def find_valid_id(session, headers, id_val):
    """Binary search: check if a single ID is valid."""
    result = await try_ids(session, headers, [id_val])
    return result is not None


async def main():
    api = mod.SystemairCloudAPI(email=os.environ["SYSTEMAIR_EMAIL"], password=os.environ["SYSTEMAIR_PASSWORD"])
    try:
        await api.login()
        print("Login OK")
        session = api._get_session()
        headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
            "device-id": os.environ["SYSTEMAIR_DEVICE_ID"],
            "device-type": "LEGACY",
        }

        # First, collect all known valid IDs from ExportDataItems
        print("\nFetching ExportDataItems for known IDs...")
        payload = {"query": "{ ExportDataItems { version type dataItems } }"}
        async with session.post(URL, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=60)) as resp:
            data = json.loads(await resp.text())
        export = data.get("data", {}).get("ExportDataItems", {})
        export_items = export.get("dataItems", [])
        if isinstance(export_items, str):
            export_items = json.loads(export_items)
        
        known_ids = set()
        for item in export_items:
            known_ids.add(item.get("id"))
        print(f"ExportDataItems has {len(known_ids)} IDs: {sorted(known_ids)[:20]}...")
        print(f"Max ID in export: {max(known_ids)}")

        # Also get IDs from /home view properties
        print("\nFetching /home view for additional IDs...")
        view_payload = {
            "query": """query ($input: GetViewInputType!) {
              GetView(input: $input) { children { properties } }
            }""",
            "variables": {"input": {"route": "/home"}}
        }
        async with session.post(URL, json=view_payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=60)) as resp:
            data = json.loads(await resp.text())
        view = data.get("data", {}).get("GetView", {})
        for child in view.get("children", []):
            props = child.get("properties")
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except:
                    continue
            if isinstance(props, dict):
                di = props.get("dataItem", {})
                if isinstance(di, dict) and "id" in di:
                    known_ids.add(di["id"])

        # Also get IDs from /service/* views
        for route in ["/service/input", "/service/output", "/service/components", 
                      "/service/control_regulation", "/service/user_modes"]:
            view_payload["variables"] = {"input": {"route": route}}
            async with session.post(URL, json=view_payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=60)) as resp:
                data = json.loads(await resp.text())
            view = data.get("data", {}).get("GetView", {})
            count = 0
            for child in view.get("children", []):
                props = child.get("properties")
                if isinstance(props, str):
                    try:
                        props = json.loads(props)
                    except:
                        continue
                if isinstance(props, dict):
                    di = props.get("dataItem", {})
                    if isinstance(di, dict) and "id" in di:
                        known_ids.add(di["id"])
                        count += 1
            print(f"  {route}: {count} data item IDs found")

        print(f"\nTotal known IDs: {len(known_ids)}")
        print(f"All known IDs (sorted): {sorted(known_ids)}")

        # Now fetch ALL known IDs and check which map to sensor registers
        print("\nFetching all known IDs to find sensor registers...")
        
        all_items = {}
        sorted_ids = sorted(known_ids)
        
        # Fetch one by one to avoid batch failures
        for item_id in sorted_ids:
            result = await try_ids(session, headers, [item_id])
            if result:
                for item in result:
                    mb = item.get("extension", {}).get("modbusRegister", 0)
                    all_items[item["id"]] = item
                    if mb in TARGETS:
                        print(f"  FOUND TARGET: ID {item['id']:4d} -> Modbus {mb:>6d} = {item.get('value')}, dec={item.get('decimals')}")
                    elif 12000 <= mb <= 14999:
                        print(f"  Sensor range: ID {item['id']:4d} -> Modbus {mb:>6d} = {item.get('value')}, dec={item.get('decimals')}")

        # Summary
        print(f"\nTotal items fetched: {len(all_items)}")
        print("\nTarget register mapping:")
        target_found = {}
        for item_id, item in all_items.items():
            mb = item.get("extension", {}).get("modbusRegister", 0)
            if mb in TARGETS:
                target_found[mb] = item
        
        for mb in sorted(TARGETS):
            if mb in target_found:
                item = target_found[mb]
                print(f"  Modbus {mb:>6d} -> ID {item['id']:4d}, value={item.get('value')}")
            else:
                print(f"  Modbus {mb:>6d} -> NOT FOUND in any known data item")

        # Save all items for reference
        with open("all_known_data_items.json", "w") as f:
            json.dump(list(all_items.values()), f, indent=2)
        print(f"\nSaved {len(all_items)} items to all_known_data_items.json")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
