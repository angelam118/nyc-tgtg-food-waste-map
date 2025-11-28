import json
import time
import os
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

SCAN_ZONES = [
    {"name": "Manhattan", "lat": 40.7831, "long": -73.9712},
    {"name": "Brooklyn", "lat": 40.6782, "long": -73.9442},
    {"name": "Queens", "lat": 40.7282, "long": -73.7949},
    {"name": "The Bronx", "lat": 40.8448, "long": -73.8648},
    {"name": "Staten Island", "lat": 40.5795, "long": -74.1502}
]

OUTPUT_FILE = 'nyc_data.json'

def get_location(store_item):
    """ Tries multiple ways to find latitude and longitude based on API variations """
    lat, lng = None, None
    
    # Check 'location' key (Old API style)
    if 'location' in store_item:
        loc = store_item['location']
        # direct
        lat = loc.get('latitude')
        lng = loc.get('longitude')
        # nested
        if not lat and 'location' in loc:
            lat = loc['location'].get('latitude')
            lng = loc['location'].get('longitude')

    # Check 'store_location' key (New API style - MATCHES YOUR DEBUG DATA)
    if not lat and 'store_location' in store_item:
        loc = store_item['store_location']
        # direct
        lat = loc.get('latitude')
        lng = loc.get('longitude')
        # nested (This is the one from your logs)
        if not lat and 'location' in loc:
            lat = loc['location'].get('latitude')
            lng = loc['location'].get('longitude')
        
    return lat, lng

def fetch_data():
    client = TgtgClient(access_token=TGTG_CREDS['access_token'], 
                        refresh_token=TGTG_CREDS['refresh_token'],
                        cookie=TGTG_CREDS['cookie'])
    client.user_id = TGTG_CREDS['user_id']

    all_stores = {} 
    
    print(f"🚀 Starting NYC Wide Scan ({len(SCAN_ZONES)} Zones)...")
    
    for zone in SCAN_ZONES:
        print(f"   📍 Scanning {zone['name']}...", end=" ")
        try:
            items = client.get_items(
                favorites_only=False,
                latitude=zone['lat'],
                longitude=zone['long'],
                radius=10, 
                page_size=300 
            )
            print(f"Found {len(items)} items.")
            
            for item in items:
                try:
                    store_id = item['item']['item_id']
                    if store_id in all_stores: continue

                    # Use updated robust location finder
                    lat, lng = get_location(item['store'])
                    
                    if not lat or not lng: 
                        continue

                    # Safe Pricing
                    price_data = item['item'].get('item_price', {}) # Changed to item_price based on your log
                    price = price_data.get('minor_units', 0) / 100
                    currency = price_data.get('code', 'USD')
                    
                    value_data = item['item'].get('item_value', {}) # Changed to item_value based on your log
                    original_price = value_data.get('minor_units', 0) / 100

                    # Image extraction (updated based on your log)
                    cover_img = item['item'].get('cover_picture', {}).get('current_url')
                    if not cover_img:
                        cover_img = item['store'].get('cover_picture', {}).get('current_url')

                    store_obj = {
                        "id": store_id,
                        "name": item['display_name'], # Using display_name from your log
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
                        "tags": [t['description'] for t in item.get('item_tags', [])], # Updated tags logic
                        "cover_image": cover_img
                    }
                    
                    all_stores[store_id] = store_obj
                    
                except Exception as e:
                    # print(f"      ❌ Failed parsing item: {e}")
                    continue

        except Exception as e:
            print(f"Error scanning zone {zone['name']}: {e}")
        
        time.sleep(2) 

    # Prepare Data
    final_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_stores": len(all_stores),
        "stores": list(all_stores.values())
    }

    # Save to file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=2)

    print(f"\n✅ Scan Complete! Saved {len(all_stores)} unique stores to {OUTPUT_FILE}")

if __name__ == "__main__":
    fetch_data()
