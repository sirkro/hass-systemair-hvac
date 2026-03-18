"""Quick script to introspect the Systemair GraphQL API schema."""
import asyncio
import json
import os
import sys

import aiohttp

# Import cloud_api directly to avoid homeassistant dependency
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cloud_api",
    os.path.join(os.path.dirname(__file__), "custom_components", "systemair", "cloud_api.py")
)
cloud_api_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud_api_mod)
SystemairCloudAPI = cloud_api_mod.SystemairCloudAPI


async def main():
    email = os.environ["SYSTEMAIR_EMAIL"]
    password = os.environ["SYSTEMAIR_PASSWORD"]
    
    api = SystemairCloudAPI(email=email, password=password)
    
    try:
        token = await api.login()
        print(f"Login OK, token starts with: {token[:20]}...")
        
        # Introspection query - get types related to Account and Device
        introspection = """
        {
          __schema {
            queryType {
              name
              fields {
                name
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
                type {
                  name
                  kind
                  ofType {
                    name
                    kind
                    fields {
                      name
                      type {
                        name
                        kind
                      }
                    }
                  }
                }
              }
            }
            mutationType {
              name
              fields {
                name
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
            }
          }
        }
        """
        
        session = api._get_session()
        headers = {
            "x-access-token": api._access_token,
            "content-type": "application/json",
        }
        
        async with session.post(
            api._api_url,
            json={"query": introspection, "variables": {}},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            print(f"Introspection HTTP status: {resp.status}")
            body = await resp.text()
            
            if resp.status == 200:
                data = json.loads(body)
                print(json.dumps(data, indent=2))
            else:
                print(f"Error body: {body[:2000]}")
        
        # Also try to get the GetAccountsWhereInput type details
        type_query = """
        {
          __type(name: "GetAccountsWhereInput") {
            name
            kind
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
        """
        
        async with session.post(
            api._api_url,
            json={"query": type_query, "variables": {}},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            print(f"\nGetAccountsWhereInput type HTTP status: {resp.status}")
            body = await resp.text()
            if resp.status == 200:
                data = json.loads(body)
                print(json.dumps(data, indent=2))
            else:
                print(f"Error body: {body[:2000]}")

        # Also try the Account type 
        account_type_query = """
        {
          __type(name: "Account") {
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
                }
              }
            }
          }
        }
        """
        
        async with session.post(
            api._api_url,
            json={"query": account_type_query, "variables": {}},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            print(f"\nAccount type HTTP status: {resp.status}")
            body = await resp.text()
            if resp.status == 200:
                data = json.loads(body)
                print(json.dumps(data, indent=2))
            else:
                print(f"Error body: {body[:2000]}")

    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
