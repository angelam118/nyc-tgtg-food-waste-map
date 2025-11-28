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

# --- BALANCED NYC GRID (8 Strategic Zones) ---
# We split dense boroughs (Manhattan/Brooklyn/Queens) into 2 parts.
# This avoids the "400 item limit" per request without needing 25 separate scans.
SCAN_ZONES = [
    # MANHATTAN (Split to catch Lower & Upper without truncation)
    {"name": "Manhattan - South (Village/Chelsea)", "lat": 40.730, "long": -74.00},
    {"name": "Manhattan - North (Harlem/UWS/UES)", "lat": 40.800, "long": -73.95},

    # BROOKLYN (Split to catch Hipster areas vs Residential)
    {"name": "Brooklyn - North (Williamsburg/Downtown)", "lat": 40.700, "long": -73.95},
    {"name": "Brooklyn - South (Flatbush/Bensonhurst)", "lat": 40.630, "long": -73.97},

    # QUEENS (Split to catch Astoria vs Flushing)
    {"name": "Queens - West (Astoria/LIC)", "lat": 40.750, "long": -73.91},
    {"name": "Queens - East (Flushing/Forest Hills)", "lat": 40.730, "long": -73.82},

    # THE REST
    {"name": "The Bronx", "lat": 40.850, "long": -73.89},
    {"name": "Staten Island", "lat": 40.580, "long": -74.15}
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
    
    print(f"🚀 Starting Balanced NYC Scan ({len(SCAN_ZONES)} Zones)...")
    
    for zone in SCAN_ZONES:
        print(f"   📍 {zone['name']}...", end=" ", flush=True)
        try:
            items = client.get_items(
                favorites_only=False,
                latitude=zone['lat'],
                longitude=zone['long'],
                radius=10, # Large radius + Split zones = Full coverage
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
            
            # Save progress immediately
            save_data(all_stores)

        except Exception as e:
            # Check for 403 (Blocked)
            if "403" in str(e):
                print(f"\n      ⚠️ BLOCKED (403). Pausing 45s...")
                time.sleep(45) 
            else:
                print(f"\n      ⚠️ Error: {e}", end=" ")
        
        # Fast sleep (2 seconds) to keep it snappy
        time.sleep(2) 

    print(f"\n✅ Scan Complete! Final count: {len(all_stores)} unique stores.")

if __name__ == "__main__":
    fetch_data()
