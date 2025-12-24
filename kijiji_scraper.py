from fastapi import FastAPI, HTTPException
import requests
import json
import re
from datetime import datetime, timezone

app = FastAPI(title="Kijiji Cars Scraper API")

URL = "https://www.kijiji.ca/b-cars-trucks/sudbury/c174l1700245"

PARAMS = {
    "address": "Spanish, ON",
    "for-sale-by": "ownr",
    "ll": "46.1947959,-82.3422779",
    "price": "0__",
    "radius": "988.0",
    "view": "list",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html",
}

COOKIES = {
    "kjses": "a3ada55c-3dda-4d3b-a2f1-5a2dc3e6d11e",
}

# =============================
# HELPERS
# =============================
def find_autos_listings(obj, results=None):
    if results is None:
        results = {}

    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("AutosListing:"):
                results[k] = v
            else:
                find_autos_listings(v, results)

    elif isinstance(obj, list):
        for item in obj:
            find_autos_listings(item, results)

    return results


def parse_kijiji_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(
            date_str, "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(
            date_str, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)


# =============================
# API ENDPOINT
# =============================
@app.get("/scrape_kijiji")
def scrape_kijiji():

    r = requests.get(
        URL,
        params=PARAMS,
        headers=HEADERS,
        cookies=COOKIES,
        timeout=30,
    )

    if r.status_code != 200:
        raise HTTPException(500, "Request failed")

    match = re.search(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
        r.text,
        re.DOTALL,
    )

    if not match:
        raise HTTPException(500, "Embedded JSON not found")

    raw_json = (
        match.group(1)
        .replace("&quot;", '"')
        .replace("&amp;", "&")
        .strip()
    )

    data = json.loads(raw_json)

    listings_map = find_autos_listings(data)
    now = datetime.now(timezone.utc)

    results = []

    for listing in listings_map.values():
        attributes = listing.get("attributes", {}).get("all", [])

        def get_attr(name):
            for a in attributes:
                if a.get("canonicalName") == name:
                    vals = a.get("canonicalValues")
                    return vals[0] if vals else None
            return None

        activation = parse_kijiji_date(listing.get("activationDate"))
        sorting = parse_kijiji_date(listing.get("sortingDate"))
        amount = listing.get("price", {}).get("amount")

        if isinstance(amount, (int, float)):
            price = amount // 100
        else:
            price = amount 
            results.append({
            "title": listing.get("title"),
            "description": listing.get("description"),
            "price": price,
            "currency": "CAD",
            "url": listing.get("url"),
            "images": listing.get("imageUrls") or [],
            "brand": get_attr("carmake"),
            "model": get_attr("carmodel"),
            "year": get_attr("caryear"),
            "mileage_km": get_attr("carmileageinkms"),
            "body_type": get_attr("carbodytype"),
            "color": get_attr("carcolor"),
            "doors": get_attr("noofdoors"),
            "fuel_type": get_attr("carfueltype"),
            "transmission": get_attr("cartransmission"),
            "activation_date": activation.isoformat() if activation else None,
            "sorting_date": sorting.isoformat() if sorting else None,
            "time_since_activation": (
                str(now - activation) if activation else None
            ),
        })

    results.sort(
        key=lambda x: x["sorting_date"] or "",
        reverse=True,
    )

    return {
        "count": len(results),
        "cars": results,
    }




