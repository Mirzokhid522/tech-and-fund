import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

notion_token = os.getenv("NOTION_TOKEN")
db_keys = ["DB_USD", "DB_AUD", "DB_EUR", "DB_GBP", "DB_CAD", "DB_CHF", "DB_JPY"]

print("=" * 60)
print("NOTION CONNECTION DIAGNOSTIC TOOL")
print("=" * 60)

if not notion_token:
    print("❌ ERROR: NOTION_TOKEN is missing from your .env file!")
    exit()
else:
    print(f"✅ FOUND: NOTION_TOKEN starts with {notion_token[:8]}...")

headers = {
    "Authorization": f"Bearer {notion_token}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

for db_key in db_keys:
    db_id = os.getenv(db_key)
    print("-" * 60)
    if not db_id:
        print(f"⚠️ WARNING: {db_key} is not set or empty in your .env file.")
        continue
        
    print(f"🔍 Testing {db_key} (ID: {db_id})...")
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    
    try:
        response = requests.post(url, headers=headers, timeout=10)
        print(f"   Response Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            print(f"   ✅ SUCCESS! Found {len(results)} pages/rows in this database.")
            
            if len(results) > 0:
                # Inspect properties of the first row to check names
                first_page = results[0]
                props = first_page.get("properties", {})
                print(f"   📋 Available properties in {db_key}:")
                for prop_name, prop_data in props.items():
                    print(f"      - Name: '{prop_name}' | Type: {prop_data.get('type')}")
            else:
                print(f"   ⚠️ Database is empty (0 rows returned).")
        else:
            print(f"   ❌ FAILED to query {db_key}.")
            print(f"   Error details: {response.text}")
            print(f"   (Tip: Make sure your Notion integration connection is added to this specific database page in Notion settings!)")
            
    except Exception as e:
        print(f"   ❌ EXCEPTION occurred: {e}")

print("=" * 60)
print("Diagnostic test complete.")
print("=" * 60)