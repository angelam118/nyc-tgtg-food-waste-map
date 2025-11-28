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

# --- DETAILED NYC GRID (25 Zones) ---
# We use small radii (4km) to ensure we don't hit the 400-item API limit per request
SCAN_ZONES = [
    # MANHATTAN
    {"name": "Manhattan - FiDi/Tribeca", "lat": 40.7127, "long": -74.0059},
    {"name": "Manhattan - Lower East Side", "lat": 40.7150, "long": -73.9843},
    {"name": "Manhattan - Chelsea/Midtown", "lat": 40.7484, "long": -73.9967},
    {"name": "Manhattan - Upper West Side", "lat": 40.7870, "long": -73.9754},
    {"name": "Manhattan - Upper East Side", "lat": 40.7736, "long": -73.9566},
    {"name": "Manhattan - Harlem/Heights", "lat": 40.8200, "long": -73.9493},
    {"name": "Manhattan - Inwood", "lat": 40.8677, "long": -73.9212},

    # BROOKLYN
    {"name": "Brooklyn - Downtown/Heights", "lat": 40.6932, "long": -73.9860},
    {"name": "Brooklyn - Williamsburg", "lat": 40.7165, "long": -73.9557},
    {"name": "Brooklyn - Park Slope", "lat": 40.6655, "long": -73.9820},
    {"name": "Brooklyn - Bed-Stuy/Bushwick", "lat": 40.6900, "long": -73.9350},
    {"name": "Brooklyn - Flatbush", "lat": 40.6400, "long": -73.9550},
    {"name": "Brooklyn - Sunset Park/Bay Ridge", "lat": 40.6413, "long": -74.0150},
    {"name": "Brooklyn - Coney Island/Bensonhurst", "lat": 40.5950, "long": -73.9900},
    {"name": "Brooklyn - East NY", "lat": 40.6600, "long": -73.8900},

    # QUEENS
    {"name": "Queens - LIC/Astoria", "lat": 40.7550, "long": -73.9250},
    {"name": "Queens - Jackson Heights", "lat": 40.7500, "long": -73.8800},
    {"name": "Queens - Flushing", "lat": 40.7600, "long": -73.8300},
    {"name": "Queens - Forest Hills", "lat": 40.7200, "long": -73.8450},
    {"name": "Queens - Jamaica", "lat": 40.7000, "long": -73.8000},
    {"name": "Queens - Rockaways", "lat": 40.5900, "long": -73.8000},

    # BRONX
    {"name": "Bronx - South", "lat": 40.8150, "long": -73.9150},
    {"name": "Bronx - Fordham", "lat": 40.8600, "long": -73.8900},
    {"name": "Bronx - East", "lat": 40.8500, "long": -73.8400},

    # STATEN ISLAND
    {"name": "Staten Island - North", "lat": 40.6300, "long": -74.1200},
    {"name": "Staten Island - Mall Area", "lat": 40.5800, "long": -74.1600}
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

def fetch_data():
    client = TgtgClient(access_token=TGTG_CREDS['access_token'], 
                        refresh_token=TGTG_CREDS['refresh_token'],
                        cookie=TGTG_CREDS['cookie'])
    client.user_id = TGTG_CREDS['user_id']

    all_stores = {} 
    
    print(f"🚀 Starting High-Res NYC Grid Scan ({len(SCAN_ZONES)} Zones)...")
    
    for zone in SCAN_ZONES:
        print(f"   📍 {zone['name']}...", end=" ", flush=True)
        try:
            items = client.get_items(
                favorites_only=False,
                latitude=zone['lat'],
                longitude=zone['long'],
                radius=4, # Smaller radius (4km) to catch all local items without hitting limit
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

        except Exception as e:
            print(f"Error scanning zone {zone['name']}: {e}")
        
        # Slightly longer sleep to be polite with 25 requests
        time.sleep(3) 

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
