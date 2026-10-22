"""Water (BGT waterdeel), the city outline and the protected townscapes, in the viewer's local frame.

townscapes.bin holds the protected town and village views (s00_fetch_rce), townscapes_edge.bin their borders as
bands EDGE metres wide; the viewer shows both on a toggle. A city without one gets neither file.

water.bin / land.bin layout (little-endian):
  u32 nPoly, nRing, nVert; u32 ringStart[nPoly+1]; u32 vertStart[nRing+1]; f32 xz[2*nVert]
First ring of each polygon is its exterior, the rest are holes.
"""
import struct
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely

from .s03_tiles import ORIGIN, to_local
from .city import DATA, WEB

EDGE = 8.0  # metres: wide enough to see from across the city

OUT = Path(WEB)


def polygons(geom):
    return [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and not g.is_empty]


def pack(geoms) -> bytes:
    ring_start, vert_start, verts = [0], [0], []
    for poly in geoms:
        for ring in [poly.exterior, *poly.interiors]:
            c = shapely.get_coordinates(ring)[:-1]
            if len(c) < 3:
                continue
            verts.append(to_local(c).astype("<f4"))
            vert_start.append(vert_start[-1] + len(c))
        ring_start.append(len(vert_start) - 1)
    V = np.concatenate(verts)
    return (struct.pack("<3I", len(ring_start) - 1, len(vert_start) - 1, len(V))
            + np.array(ring_start, "<u4").tobytes() + np.array(vert_start, "<u4").tobytes() + V.tobytes())


def main():
    city = gpd.read_file(f"{DATA}/raw/boundary.json").set_crs(28992, allow_override=True).union_all()
    w = gpd.read_file(f"{DATA}/raw/bgt_waterdeel.geojson").set_crs(28992, allow_override=True)
    w = w[w.relatieve_hoogteligging == 0]
    water = shapely.make_valid(w.union_all()).intersection(city)
    water = water.buffer(0.5).buffer(-0.5).simplify(1.0)
    water = [p for p in polygons(water) if p.area > 30]
    land = city.difference(shapely.MultiPolygon(water)).simplify(1.0)
    land = [p for p in polygons(land) if p.area > 30]
    (OUT / "water.bin").write_bytes(pack(water))
    (OUT / "land.bin").write_bytes(pack(land))
    print(f"water {len(water)} polys {sum(p.area for p in water)/1e6:.1f} km², {(OUT/'water.bin').stat().st_size/1e6:.2f} MB;"
          f" land {len(land)} polys, {(OUT/'land.bin').stat().st_size/1e6:.2f} MB")

    gz = Path(f"{DATA}/raw/layers/gezichten.geojson")
    for f in ("townscapes.bin", "townscapes_edge.bin"):
        (OUT / f).unlink(missing_ok=True)
    if gz.exists():
        g = gpd.read_file(gz).set_crs(28992, allow_override=True)
        if len(g):
            shapes = [shapely.make_valid(x).simplify(1.0) for x in g.geometry]
            area = [p for x in shapes for p in polygons(x)]
            edge = [p for x in shapes for p in polygons(x.boundary.buffer(EDGE / 2, cap_style="flat").simplify(0.5))]
            (OUT / "townscapes.bin").write_bytes(pack(area))
            (OUT / "townscapes_edge.bin").write_bytes(pack(edge))
            print(f"{len(g)} protected townscapes, {sum(p.area for p in area)/1e6:.2f} km²")


if __name__ == "__main__":
    main()
