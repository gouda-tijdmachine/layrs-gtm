"""The municipality's outline from Kadaster's Bestuurlijke Gebieden (PDOK OGC API, CC0), in RD New: raw/boundary.json."""
import json
from pathlib import Path

import requests

from .city import DATA, GEMEENTE_CODE, UA

API = "https://api.pdok.nl/kadaster/bestuurlijkegebieden/ogc/v1/collections/gemeentegebied/items"
RD = "http://www.opengis.net/def/crs/EPSG/0/28992"


def main():
    r = requests.get(API, headers=UA, timeout=120,
                     params={"f": "json", "identificatie": f"GM{GEMEENTE_CODE}", "crs": RD})
    r.raise_for_status()
    d = r.json()
    assert len(d["features"]) == 1, f"GM{GEMEENTE_CODE}: {len(d['features'])} features"
    Path(f"{DATA}/raw/boundary.json").write_text(json.dumps(d), encoding="utf-8")
    print(d["features"][0]["properties"]["naam"])


if __name__ == "__main__":
    main()
