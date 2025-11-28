import json
import time
import os
import random
from tgtg import TgtgClient
from datetime import datetime

# --- CONFIGURATION ---
try:
    TGTG_CREDS = {
        'access_token': os.environ.get("TGTG_ACCESS_TOKEN"),
        'refresh_token': os.environ.get("TGTG_REFRESH_TOKEN"),
        'user_id': os.environ.get("TGTG_USER_ID"),
        'cookie': os.environ.get("TGTG_COOKIE", "datadome=123") 
    }
    # Fallback for local testing
    if not TGTG_CREDS['access_token']:
        # PASTE YOUR HARDCODED TOKENS HERE IF RUNNING LOCALLY
        TGTG_CREDS['access_token'] = 'YOUR_ACCESS_TOKEN'
        TGTG_CREDS['refresh_token'] = 'YOUR_REFRESH_TOKEN'
        TGTG_CREDS['user_id'] = 'YOUR_USER_ID'
        
except KeyError:
    print("❌ Error: Credentials issue.")
    exit(1)

# Mimic a real iPhone to avoid being blocked
USER_AGENT = "TGTG/24.9.1 Darwin/21.6.0 (iPhone 13; iOS 15.6.1; Scale/3.00)"

# --- OPTIMIZED NYC GRID (10 Core Zones) ---
# Reduced from 25 to 10 to prevent blocking and speed up scanning.
# Radius increased to 6km to maintain coverage with fewer requests.
SCAN_ZONES = [
    # MANHATTAN (Consolidated)
    {"name": "Manhattan - Lower (FiDi/Village)", "lat": 40.725, "long": -74.00},
    {"name": "Manhattan - Mid (Chelsea/Midtown)", "lat": 40.755, "long": -73.98},
    {"name": "Manhattan - Upper (UWS/UES/Harlem)", "lat": 40.800, "long": -73.95},
    {"name": "Manhattan - North (Inwood/Wash Hts)", "lat": 40.850, "long": -73.93},

    # BROOKLYN (Consolidated)
    {"name": "Brooklyn - North (Williamsburg/Bushwick)", "lat": 40.710, "long": -73.94},
    {"name": "Brooklyn - Core (Downtown/Park Slope)", "lat": 40.670, "long": -73.98},
    {"name": "Brooklyn - South (Flatbush/Bay Ridge)", "lat": 40.630, "long": -74.00},

    # QUEENS (Consolidated)
    {"name": "Queens - West (LIC/Astoria/Sunnyside)", "lat": 40.750, "long": -73.91},
    {"name": "Queens - Central (Forest Hills/Flushing)", "lat": 40.730, "long": -73.83},

    # BRONX (Consolidated)
    {"name": "Bronx - Core", "lat": 40.850, "long": -73.89},
]

OUTPUT_FILE = 'nyc_data.json'

def get_location(store_item):
    """ Tries multiple ways to find latitude and longitude based on API variations """
    lat, lng = None, None
    
    # Check 'location' key (Old API style)
    if 'location' in store_item:
        loc = store_item['location']
        lat = loc.get('latitude')
        lng = loc.get('longitude')
        if not lat and 'location' in loc:
            lat = loc['location'].get('latitude')
            lng = loc['location'].get('longitude')

    # Check 'store_location' key (New API style)
    if not lat and 'store_location' in store_item:
        loc = store_item['store_location']
        lat = loc.get('latitude')
        lng = loc.get('longitude')
        if not lat and 'location' in loc:
            lat = loc['location'].get('latitude')
            lng = loc['location'].get('longitude')
        
    return lat, lng

def save_data(all_stores):
    """ Helper to save data immediately """
    final_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_stores": len(all_stores),
        "stores": list(all_stores.values())
    }
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=2)

def fetch_data():
    client = TgtgClient(access_token=TGTG_CREDS['access_token'], 
                        refresh_token=TGTG_CREDS['refresh_token'],
                        cookie=TGTG_CREDS['cookie'],
                        user_agent=USER_AGENT) 
    client.user_id = TGTG_CREDS['user_id']

    all_stores = {} 
    
    print(f"🚀 Starting Optimized NYC Scan ({len(SCAN_ZONES)} Zones)...")
    
    for zone in SCAN_ZONES:
        print(f"   📍 {zone['name']}...", end=" ", flush=True)
        try:
            items = client.get_items(
                favorites_only=False,
                latitude=zone['lat'],
                longitude=zone['long'],
                radius=6, # Increased radius for fewer requests
                page_size=400 
            )
            print(f"Found {len(items)} items.")
            
            for item in items:
                try:
                    store_id = item['item']['item_id']
                    if store_id in all_stores: continue

                    lat, lng = get_location(item['store'])
                    
                    if not lat or not lng: continue

                    # Safe Pricing
                    price_data = item['item'].get('item_price', {}) 
                    price = price_data.get('minor_units', 0) / 100
                    currency = price_data.get('code', 'USD')
                    
                    value_data = item['item'].get('item_value', {}) 
                    original_price = value_data.get('minor_units', 0) / 100

                    # Image extraction
                    cover_img = item['item'].get('cover_picture', {}).get('current_url')
                    if not cover_img:
                        cover_img = item['store'].get('cover_picture', {}).get('current_url')

                    # Parse Display Name carefully
                    display_name = item.get('display_name') or item['store']['store_name']

                    store_obj = {
                        "id": store_id,
                        "name": display_name,
                        "lat": lat,
                        "lng": lng,
                        "available": item['items_available'],
                        "rating": item['item'].get('average_overall_rating', {}).get('average_overall_rating', 0),
                        "ratings_count": item['item'].get('average_overall_rating', {}).get('rating_count', 0),
                        "price": price,
                        "original_price": original_price,
                        "currency": currency,
                        "category": item['item'].get('item_category', 'Unknown'),
                        "pickup_start": item.get('pickup_interval', {}).get('start'),
                        "pickup_end": item.get('pickup_interval', {}).get('end'),
                        "tags": [t['description'] for t in item.get('item_tags', [])],
                        "cover_image": cover_img
                    }
                    
                    all_stores[store_id] = store_obj
                    
                except Exception:
                    continue
            
            # INCREMENTAL SAVE: Save after every zone so we don't lose data if blocked later
            save_data(all_stores)

        except Exception as e:
            # Check for 403 (Blocked)
            if "403" in str(e):
                print(f"\n      ⚠️ BLOCKED (403). Waiting 2 minutes before next zone...")
                time.sleep(120) # 2 minute cool down
            else:
                print(f"\n      ⚠️ Error: {e}", end=" ")
        
        # Random sleep between 15 and 30 seconds to look human
        nap_time = random.uniform(15, 30)
        time.sleep(nap_time) 

    print(f"\n✅ Scan Complete! Final count: {len(all_stores)} unique stores.")

if __name__ == "__main__":
    fetch_data()
