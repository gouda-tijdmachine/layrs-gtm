"""Fetch the city's national monuments from the RCE register (CC0); see rce.py for the two routes in.

Writes what the Amsterdam pipeline takes from the city API and from exports, in the same shapes, so every later
step works for any municipality:
  raw/layers/monuments.json     [{nr, status, name, function, styles, years, panden: [BAG pand id], ...}]
  raw/rce_descriptions.csv      nr, txt: the register's description, read by monuments.py and the layers
  raw/layers/rce_styles.json    [{nr, style}]
  raw/layers/gezichten.geojson  protected townscapes overlapping the municipality, RD New
  raw/layers/rce_actors.json    [{nr, actor, name, role}]: makers and clients, for the graph (s13_graph_rce)
A monument's panden are the ones the register names, plus the panden of the verblijfsobjecten it names (BAG,
raw/verblijfsobjecten.json from s00_fetch_addresses).
"""
import csv
import json
from pathlib import Path

import geopandas as gpd
import shapely

from . import rce
from .city import CFG, DATA, LABEL, UA

GEMEENTE = CFG.get("gemeentenaam", LABEL)  # as the register writes it, e.g. "'s-Hertogenbosch"
OUT = Path(f"{DATA}/raw/layers")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        mons = rce.from_elastic(GEMEENTE, UA)
        print(len(mons), "rijksmonumenten from Elastic (Erfgoed-ceo),", sum(bool(m["years"]) for m in mons), "with building years")
    except Exception as e:
        print("Elastic failed, falling back to SPARQL:", e)
        mons = rce.from_sparql(GEMEENTE, UA)
        print(len(mons), "rijksmonumenten from SPARQL")

    vbo_pand = json.loads(Path(f"{DATA}/raw/verblijfsobjecten.json").read_text())
    links = rce.bag_links(GEMEENTE, UA)
    for m in mons:
        panden, vbos = links.get(m["nr"], (set(), set()))
        vbos = vbos | set(m["vbos"])
        m["vbos"] = sorted(vbos)
        m["panden"] = sorted(panden | {vbo_pand[v] for v in vbos if vbo_pand.get(v)})
    (OUT / "monuments.json").write_text(json.dumps(mons, ensure_ascii=False), encoding="utf-8")
    print(sum(bool(m["panden"]) for m in mons), "of them on a BAG pand,", len({p for m in mons for p in m["panden"]}), "panden")

    with open(f"{DATA}/raw/rce_descriptions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["nr", "txt"])
        w.writeheader()
        w.writerows(dict(nr=m["nr"], txt=m["txt"]) for m in mons if m["txt"])
    (OUT / "rce_styles.json").write_text(json.dumps(
        [dict(nr=m["nr"], style=s) for m in mons for s in m["styles"]], ensure_ascii=False), encoding="utf-8")

    act = rce.actors(GEMEENTE, UA)
    (OUT / "rce_actors.json").write_text(json.dumps(act, ensure_ascii=False), encoding="utf-8")
    print(len(act), "makers and clients of", len({a["nr"] for a in act}), "monuments")

    city = gpd.read_file(f"{DATA}/raw/boundary.json").set_crs(28992, allow_override=True).union_all()
    rows = rce.townscapes(UA)
    g = gpd.GeoDataFrame([{k: r.get(k) for k in ("nr", "naam", "status")} for r in rows],
                         geometry=[shapely.from_wkt(r["wkt"]) for r in rows], crs=4326).to_crs(28992)
    g = g[g.intersects(city) & (g.status != "ingetrokken")]
    g.to_file(OUT / "gezichten.geojson", driver="GeoJSON")
    print(len(g), "protected townscapes:", ", ".join(sorted(g.naam.fillna("?"))))


if __name__ == "__main__":
    main()
