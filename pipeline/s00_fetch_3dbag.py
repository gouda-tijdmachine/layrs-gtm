"""Download the 3D BAG tiles that cover the municipality (TU Delft 3D geoinformation, CC BY 4.0) into raw/3dbag/.

The tile index (FlatGeobuf) lists every tile with its outline and the URL of its GeoPackage; only the tiles that
touch the municipality's outline are fetched. A tile already on disk is kept, so a broken run can simply be rerun.
When the server cannot be reached the step says so and stops without an error: s00_fetch_3dbv then fetches the
3D Basisvoorziening, from which s01_load builds the same tables without LoD 2.2 roofs.
"""
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import requests

from .city import DATA, UA

INDEX = "https://data.3dbag.nl/v20250903/tile_index.fgb"  # release of 3 September 2025
OUT = Path(f"{DATA}/raw/3dbag")


def fetch(tile_id: str, url: str) -> str:
    name = tile_id.replace("/", "-")
    target = OUT / f"{name}.gpkg"
    if target.exists():
        return "kept"
    for attempt in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=600)
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 3:
                raise
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            member = next(n for n in z.namelist() if n.endswith(".gpkg"))
            target.write_bytes(z.read(member))
    else:
        target.write_bytes(r.content)
    return "new"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    city = gpd.read_file(f"{DATA}/raw/boundary.json").set_crs(28992, allow_override=True)
    try:
        tiles = gpd.read_file(INDEX, bbox=tuple(city.total_bounds)).to_crs(28992)
    except Exception as e:
        print(f"3D BAG out of reach ({type(e).__name__}): falling back to the 3D Basisvoorziening")
        return
    tiles = tiles[tiles.intersects(city.union_all())]
    print(len(tiles), "tiles")
    with ThreadPoolExecutor(4) as ex:
        done = list(ex.map(fetch, tiles.tile_id, tiles.gpkg_download))
    print(done.count("new"), "downloaded,", done.count("kept"), "already there")


if __name__ == "__main__":
    main()
