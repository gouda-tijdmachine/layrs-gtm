"""Building heights from Kadaster's 3D Basisvoorziening (PDOK, CC BY 4.0): the fallback when 3D BAG is out of reach.

Its 'hoogtestatistieken gebouwen' are the same reconstruction as 3D BAG (the roofer tool on AHN and aerial
images): per BAG pand its footprint, construction year, ground level and roof heights (rf_h_ground, rf_h_roof_50p,
70p, max, NAP), but no LoD 1.3 parts and no LoD 2.2 roof faces. s01_load reads these tiles when raw/3dbag/ is empty,
so every building stands as one prism of its 70th-percentile roof height. Only the newest year is fetched, in the
5 x 6.25 km sheets that touch the municipality, into raw/3dbv/.
"""
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import requests

from .city import DATA, UA

INDEX = "https://api.pdok.nl/kadaster/3d-basisvoorziening/ogc/v1/collections/hoogtestatistieken_gebouwen/items"
RD = "http://www.opengis.net/def/crs/EPSG/0/28992"
OUT = Path(f"{DATA}/raw/3dbv")


def sheets(bbox) -> gpd.GeoDataFrame:
    url, params, feats = INDEX, {"f": "json", "limit": 1000, "bbox": ",".join(map(str, bbox)), "bbox-crs": RD, "crs": RD}, []
    while url:
        d = requests.get(url, params=params, headers=UA, timeout=120).json()
        feats += d["features"]
        url = next((l["href"] for l in d["links"] if l["rel"] == "next"), None)
        params = None
    return gpd.GeoDataFrame.from_features(feats, crs=28992)


def fetch(url: str) -> str:
    target = OUT / url.rsplit("/", 1)[1].replace(".zip", ".gpkg")
    if target.exists():
        return "kept"
    r = requests.get(url, headers=UA, timeout=600)  # follows the redirect to 3d.kadaster.nl
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        target.write_bytes(z.read(next(n for n in z.namelist() if n.endswith(".gpkg"))))
    return "new"


def main():
    if any(Path(f"{DATA}/raw/3dbag").glob("*.gpkg")):
        print("3D BAG tiles present: the 3D Basisvoorziening is not needed")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    city = gpd.read_file(f"{DATA}/raw/boundary.json").set_crs(28992, allow_override=True)
    s = sheets(tuple(round(v) for v in city.total_bounds))
    s = s[s.intersects(city.union_all())]
    year = s.jaargang_luchtfoto.max()
    s = s[s.jaargang_luchtfoto == year]
    print(len(s), f"sheets of {year}")
    with ThreadPoolExecutor(4) as ex:
        done = list(ex.map(fetch, s.download_link))
    print(done.count("new"), "downloaded,", done.count("kept"), "already there")


if __name__ == "__main__":
    main()
