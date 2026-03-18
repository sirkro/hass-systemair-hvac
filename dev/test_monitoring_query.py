"""Test GetUnitMonitoringDataItems to see if it returns sensor INPUT register data."""
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

# Registers we want to test (0-indexed Modbus registers)
TEST_REGISTERS_0INDEXED = [
    12101,  # REG_SENSOR_OAT (outdoor air temp)
    12102,  # REG_SENSOR_SAT (supply air temp)
    12107,  # REG_SENSOR_OHT (overheat temp)
    12135,  # REG_SENSOR_RHS_PDM (humidity)
    12543,  # REG_SENSOR_PDM_EAT_VALUE (extract air temp)
    12400,  # REG_SENSOR_RPM_SAF
    12401,  # REG_SENSOR_RPM_EAF
    14000,  # REG_OUTPUT_SAF (fan speed %)
    14001,  # REG_OUTPUT_EAF (fan speed %)
    14100,  # REG_OUTPUT_Y1_ANALOG (heater output)
    14101,  # REG_OUTPUT_Y1_DIGITAL (heater active)
    14200,  # REG_OUTPUT_Y3_ANALOG (cooler output)
    14201,  # REG_OUTPUT_Y3_DIGITAL (cooler active)
    1160,   # REG_USERMODE_MODE
    1110,   # REG_USERMODE_REMAINING_TIME_L
    1111,   # REG_USERMODE_REMAINING_TIME_H
]

# 1-indexed (Modbus convention used in const.py)
TEST_REGISTERS_1INDEXED = [r + 1 for r in TEST_REGISTERS_0INDEXED]

REGISTER_NAMES = {
    12101: "OAT(0)", 12102: "SAT(0)/OAT(1)", 12103: "SAT(1)",
    12107: "OHT(0)", 12108: "OHT(1)",
    12135: "RHS_PDM(0)", 12136: "RHS_PDM(1)",
    12543: "EAT(0)", 12544: "EAT(1)",
    12400: "RPM_SAF(0)", 12401: "RPM_SAF(1)/RPM_EAF(0)", 12402: "RPM_EAF(1)",
    14000: "OUT_SAF(0)", 14001: "OUT_SAF(1)/OUT_EAF(0)", 14002: "OUT_EAF(1)",
    14100: "Y1_ANA(0)", 14101: "Y1_ANA(1)/Y1_DIG(0)", 14102: "Y1_DIG(1)",
    14200: "Y3_ANA(0)", 14201: "Y3_ANA(1)/Y3_DIG(0)", 14202: "Y3_DIG(1)",
    1160: "USERMODE(0)", 1161: "USERMODE(1)",
    1110: "REMAIN_L(0)", 1111: "REMAIN_L(1)/REMAIN_H(0)", 1112: "REMAIN_H(1)",
}


async def gql(session, headers, url, query, variables=None):
    payload = {"query": query, "variables": variables or {}}
    async with session.post(url, json=payload, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=60)) as resp:
        return resp.status, await resp.text()


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]

    api = SystemairCloudAPI(email=email, password=password)
    try:
        await api.login()
        print("Login OK\n")
        session = api._get_session()
        headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
            "device-id": DEVICE_ID,
            "device-type": "LEGACY",
        }

        query = """
        query ($input: UnitMonitoringDataItemsInput) {
          GetUnitMonitoringDataItems(input: $input) {
            register
            value
          }
        }
        """

        # Test 1: 0-indexed registers
        print("=== Test 1: 0-indexed registers ===")
        status, body = await gql(session, headers, REMOTE_API_URL, query,
                                 variables={"input": {"register": TEST_REGISTERS_0INDEXED}})
        print(f"HTTP {status}")
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {json.dumps(data['errors'][:3], indent=2)}")
        result = data.get("data", {}).get("GetUnitMonitoringDataItems")
        if result:
            print(f"Got {len(result)} items:")
            for item in result:
                reg = item['register']
                name = REGISTER_NAMES.get(reg, "???")
                print(f"  Register {reg:>6d} ({name:>20s}): {item['value']}")
        else:
            print("No results")

        # Test 2: 1-indexed registers
        print("\n=== Test 2: 1-indexed registers ===")
        status, body = await gql(session, headers, REMOTE_API_URL, query,
                                 variables={"input": {"register": TEST_REGISTERS_1INDEXED}})
        print(f"HTTP {status}")
        data = json.loads(body)
        if data.get("errors"):
            print(f"Errors: {json.dumps(data['errors'][:3], indent=2)}")
        result = data.get("data", {}).get("GetUnitMonitoringDataItems")
        if result:
            print(f"Got {len(result)} items:")
            for item in result:
                reg = item['register']
                name = REGISTER_NAMES.get(reg, "???")
                print(f"  Register {reg:>6d} ({name:>20s}): {item['value']}")
        else:
            print("No results")

        # Test 3: route-based (returns all monitoring registers for a page)
        for route in ["/device/home", "/device/monitoring"]:
            print(f"\n=== Test 3: route={route} ===")
            status, body = await gql(session, headers, REMOTE_API_URL, query,
                                     variables={"input": {"route": route}})
            print(f"HTTP {status}")
            data = json.loads(body)
            if data.get("errors"):
                print(f"Errors: {data['errors'][0].get('message', '')[:200]}")
            result = data.get("data", {}).get("GetUnitMonitoringDataItems")
            if result:
                print(f"Got {len(result)} items:")
                for item in result:
                    reg = item['register']
                    name = REGISTER_NAMES.get(reg, "???")
                    print(f"  Register {reg:>6d} ({name:>20s}): {item['value']}")
            else:
                print("No results")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
