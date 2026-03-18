"""Targeted introspection for Device type and device-related queries."""
import asyncio
import json
import os
import sys
import importlib.util

import aiohttp

spec = importlib.util.spec_from_file_location(
    "cloud_api",
    os.path.join(os.path.dirname(__file__), "custom_components", "systemair", "cloud_api.py")
)
cloud_api_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud_api_mod)
SystemairCloudAPI = cloud_api_mod.SystemairCloudAPI


async def introspect_type(session, api, type_name):
    """Introspect a specific type."""
    query = """
    {
      __type(name: "%s") {
        name
        kind
        fields {
          name
          type {
            name
            kind
            ofType {
              name
              kind
              ofType {
                name
                kind
              }
            }
          }
          args {
            name
            type {
              name
              kind
              ofType {
                name
                kind
              }
            }
          }
        }
        inputFields {
          name
          type {
            name
            kind
            ofType {
              name
              kind
            }
          }
        }
      }
    }
    """ % type_name

    headers = {
        "x-access-token": api._access_token,
        "content-type": "application/json",
    }
    
    async with session.post(
        api._api_url,
        json={"query": query, "variables": {}},
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        body = await resp.text()
        if resp.status == 200:
            data = json.loads(body)
            return data
        return {"error": body[:500]}


async def try_query(session, api, name, query, variables=None):
    """Try a GraphQL query and print result."""
    headers = {
        "x-access-token": api._access_token,
        "content-type": "application/json",
    }
    
    payload = {"query": query, "variables": variables or {}}
    
    async with session.post(
        api._api_url,
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        body = await resp.text()
        print(f"\n=== {name} (HTTP {resp.status}) ===")
        if len(body) > 3000:
            print(body[:3000] + "... (truncated)")
        else:
            print(body)


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]
    
    api = SystemairCloudAPI(email=email, password=password)
    
    try:
        token = await api.login()
        print(f"Login OK")
        
        session = api._get_session()

        # 1. Introspect key types
        for type_name in ["Device", "DeviceStatus", "DeviceTypeProperties", 
                          "GetDeviceViewInput", "WriteDeviceValuesInputType",
                          "WriteDeviceValuesInput"]:
            result = await introspect_type(session, api, type_name)
            print(f"\n=== Type: {type_name} ===")
            print(json.dumps(result, indent=2))
        
        # 2. Try GetAccountDevices query (the parameterless one from schema)
        await try_query(session, api, "GetAccountDevices", """{
          GetAccountDevices {
            identifier
            name
            status {
              connectionStatus
              latestSync
            }
          }
        }""")
        
        # 3. Try GetLoggedInUser
        await try_query(session, api, "GetLoggedInUser", """{
          GetLoggedInUser {
            account {
              email
              firstName
              lastName
            }
          }
        }""")
        
        # 4. Try GetDeviceView mutation (may still work even if not in main schema)
        await try_query(session, api, "GetDeviceView (reference style)", """
            mutation ($input: GetDeviceViewInput!) {
              GetDeviceView(input: $input) {
                route
                elements
                dataItems
                title
                translationVariables
              }
            }
        """, variables={"input": {"deviceId": "PLACEHOLDER", "route": "/device/home"}})
        
        # 5. Try WriteDeviceValues with old type name
        await try_query(session, api, "WriteDeviceValues (InputType)", """
            mutation ($input: WriteDeviceValuesInputType!) {
              WriteDeviceValues(input: $input)
            }
        """, variables={"input": {"deviceId": "PLACEHOLDER", "import": False, "registerValues": "[]"}})
        
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
