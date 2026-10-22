"""Verify the curated entries against their Wikipedia articles and geocode them to BAG buildings."""
import csv
import json
import re
from functools import cache
from urllib.parse import quote

import geopandas as gpd
import requests
from shapely.geometry import Point

from .curated import CURATED
from .city import DATA

UA = {"User-Agent": "amsterdam-by-building/0.1 (https://stop-token.com/lab/amsterdam/)"}


@cache
def article(ref):
    lang, title = ref.split(":", 1)
    r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", headers=UA, timeout=60, params={
        "action": "query", "prop": "extracts|info", "inprop": "url", "explaintext": 1, "redirects": 1,
        "format": "json", "titles": title}).json()
    page = next(iter(r["query"]["pages"].values()))
    return (page.get("extract") or ""), page.get("fullurl")


@cache
def buildings():
    b = gpd.read_parquet(f"{DATA}/buildings.parquet", columns=["identificatie", "geometry"])
    b["bag"] = b.identificatie.str.slice(-16)
    return b


def geocode(address):
    r = requests.get("https://api.pdok.nl/bzk/locatieserver/search/v3_1/free", headers=UA, timeout=60, params={
        "q": address, "fq": ["type:adres", "woonplaatsnaam:Amsterdam"], "rows": 5,
        "fl": "weergavenaam,centroide_rd"}).json()
    # Exact address only: the first result must start with the street and house number as written.
    exact = re.compile(re.escape(address) + r"(?:[A-Za-z]|-\w+)?,", re.I)  # 444, 444A, 444-1
    docs = [d for d in r["response"]["docs"] if exact.match(d["weergavenaam"])]
    if not docs:
        return None, None
    x, y = map(float, docs[0]["centroide_rd"][6:-1].split())
    b = buildings()
    hit = b[b.contains(Point(x, y))]
    if hit.empty:
        d = b.distance(Point(x, y))
        hit = b[d == d.min()] if d.min() < 15 else hit
    return (hit.bag.iloc[0] if not hit.empty else None), docs[0]["weergavenaam"]


@cache
def wikidata_bags():
    """Wikipedia article URL → BAG ids of the building it is about, from Wikidata (P5208).
    Ids no longer in BAG are left out (the Scheepvaarthuis carried a retired one); callers then geocode."""
    live = set(buildings().bag)
    out = {}
    for r in csv.DictReader(open(f"{DATA}/raw/wd_buildings.csv")):
        for k in ("en", "nl"):
            if r[k] and r["bag"].zfill(16) in live:
                out.setdefault(r[k], set()).add(r["bag"].zfill(16))
    return out


def main():
    out, dropped = [], []
    for L in CURATED:
        entries = []
        for name, address, story, ref, checks, *group in L["entries"]:
            text, url = article(ref)
            missing = [c for c in checks if c not in text]
            # An article about the building itself names its BAG ids in Wikidata: trust those over the
            # geocoder, which can land on a neighbouring part of a large complex (the Palace, the Scheepvaarthuis).
            own = wikidata_bags().get(url)
            bags, found = (sorted(own), "wikidata") if own else ((lambda b, f: ([b] if b else [], f))(*geocode(address)))
            if missing or not bags:
                dropped.append((L["id"], name, missing, found))
                continue
            for bag in bags:
                entries.append(dict(name=name, address=address, bag=bag, story=story, source=url,
                                    group=group[0] if group else L["id"]))
        out.append(dict({k: v for k, v in L.items() if k != "entries"}, entries=entries))
        print(f'{L["id"]:10s} {len(entries)}/{len(L["entries"])}')
    for d in dropped:
        print("dropped:", d)
    json.dump(out, open(f"{DATA}/curated.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
