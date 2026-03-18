"""Exhaustive scan of ALL data item IDs 0-2000 with concurrency."""
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


async def fetch_id(session, headers, id_val, semaphore):
    async with semaphore:
        payload = {"query": QUERY, "variables": {"input": [id_val]}}
        try:
            async with session.post(URL, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = json.loads(await resp.text())
        except Exception:
            return None

        if data.get("errors"):
            return None

        items = data.get("data", {}).get("GetDataItems")
        if not items:
            return None
        if isinstance(items, str):
            items = json.loads(items)

        for item in items:
            if item["id"] == id_val:
                return item
    return None


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

        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests

        # Scan IDs 0-2000
        tasks = []
        for id_val in range(0, 2001):
            tasks.append(fetch_id(session, headers, id_val, semaphore))

        print("Scanning IDs 0-2000 with 10 concurrent requests...")
        results = await asyncio.gather(*tasks)

        valid_ids = {}
        for id_val, result in enumerate(results):
            if result is not None:
                mb = result.get("extension", {}).get("modbusRegister", 0)
                valid_ids[id_val] = {
                    "modbus": mb,
                    "value": result.get("value"),
                    "decimals": result.get("decimals"),
                    "readOnly": result.get("readOnly"),
                }

        print(f"\nTotal valid IDs found: {len(valid_ids)}")

        # Print all IDs in sensor/output register range
        print("\nAll IDs mapping to registers 12000-14999:")
        for id_val in sorted(valid_ids.keys()):
            info = valid_ids[id_val]
            mb = info["modbus"]
            if 12000 <= mb <= 14999:
                marker = " <<<TARGET" if mb in TARGETS else ""
                print(f"  ID {id_val:4d} -> Modbus {mb:>6d} = {info['value']}, dec={info['decimals']}, RO={info['readOnly']}{marker}")

        # Print target register results
        print("\nTarget register mapping:")
        for mb_target in sorted(TARGETS):
            found_items = [(id_val, info) for id_val, info in valid_ids.items() if info["modbus"] == mb_target]
            if found_items:
                for id_val, info in found_items:
                    print(f"  Modbus {mb_target:>6d} -> ID {id_val}, value={info['value']}, dec={info['decimals']}")
            else:
                print(f"  Modbus {mb_target:>6d} -> NOT FOUND")

        # Save
        with open("all_valid_data_items_scan.json", "w") as f:
            json.dump(valid_ids, f, indent=2, default=str)
        print(f"\nSaved to all_valid_data_items_scan.json")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
