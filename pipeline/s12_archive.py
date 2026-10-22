"""Archive photos from the Stadsarchief Amsterdam beeldbank for buildings that have no Wikimedia photo.

The Amsterdam Time Machine (University of Amsterdam) publishes the beeldbank metadata as linked data, and links
about 86,000 images to the BAG buildings they show (hasOrHadSubjectBuilding). That link is the archive's own,
so no geocoding is needed here.

1. Page through the Beeldbank-SAA search index for every image linked to a building.
2. Look up the names of photographers and makers, and the kind of document (photo, drawing, print).
3. Per building keep up to six pictures, the clearest of each decade: one that shows few buildings, a photo over a
   drawing, taken in or after the building's own year (an older picture shows whatever stood there before).
4. Write the picks into small shards, web/data/archive/<nn>.json, that the page loads when a card needs them.
"""
import json
import time
import zlib
from pathlib import Path

import pandas as pd
import requests
from .city import DATA, WEB

UA = {"User-Agent": "amsterdam-by-building/0.1 (https://stop-token.com/lab/amsterdam/)"}
KG = "https://api.lod.uba.uva.nl/datasets/ATM/ATM-KG/services/ATM-KG/sparql"
ES = "https://api.lod.uba.uva.nl/datasets/ATM/Beeldbank-SAA/services/Beeldbank-SAA/_search"
CACHE = Path(f"{DATA}/raw/saa/images.jsonl")
NAMES = Path(f"{DATA}/raw/saa/names.json")
OUT = Path(f"{WEB}/archive")
SHARDS = 64
REC = "https://ams-migrate.memorix.io/resources/records/"
CONCEPT = "https://ams-migrate.memorix.io/resources/vocabularies/concepts/"
THUMB = "https://images.memorix.nl/ams/thumb/350x350/"
F = lambda name: name.replace(".", " ")  # the index keeps predicate IRIs with dots turned into spaces
BUILDING = F("https://data.archief.amsterdam/ontology#hasOrHadSubjectBuilding")
TITLE = F("https://www.ica.org/standards/RiC/ontology#title")
BEGIN = F("https://www.ica.org/standards/RiC/ontology#hasBeginningDate")
DATE = F("https://www.ica.org/standards/RiC/ontology#textualValue")
FORM = F("https://www.ica.org/standards/RiC/ontology#hasDocumentaryFormType")
AGENT = F("https://data.archief.amsterdam/ontology#hasAgent")
THUMBNAIL = F("http://schema.org/thumbnailUrl")
LABEL = F("http://www.w3.org/2004/02/skos/core#prefLabel")
PER_BUILDING = 6


def search(body):
    for attempt in range(6):
        try:
            r = requests.post(ES, json=body, headers=UA, timeout=120)
            if r.ok:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    raise RuntimeError("beeldbank index does not answer")


def harvest():
    if CACHE.exists():
        return [json.loads(l) for l in CACHE.open()]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    rows, after = [], None
    while True:
        body = {"query": {"exists": {"field": BUILDING}}, "size": 1000, "sort": [{"@id.keyword": "asc"}],
                "_source": ["@id", BUILDING, TITLE, BEGIN, DATE, FORM, AGENT, THUMBNAIL]}
        if after:
            body["search_after"] = after
        hits = search(body)["hits"]["hits"]
        if not hits:
            break
        for h in hits:
            s = h["_source"]
            rows.append(dict(id=s["@id"].removeprefix(REC), panden=[p.rsplit("/", 1)[1] for p in s.get(BUILDING, [])],
                             title=(s.get(TITLE) or [""])[0], begin=(s.get(BEGIN) or [""])[0], date=(s.get(DATE) or [""])[0],
                             form=(s.get(FORM) or [""])[0].rsplit("/", 1)[-1], agents=[a.removeprefix(REC) for a in s.get(AGENT, [])],
                             thumb=(s.get(THUMBNAIL) or [""])[0]))
        after = hits[-1]["sort"]
        print(len(rows), end="\r")
    with CACHE.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


def names(forms):
    """Labels of document kinds from the index; names of makers from the knowledge graph (the index lacks them)."""
    if NAMES.exists():
        return json.loads(NAMES.read_text())
    known = {}
    todo = sorted(forms)
    for i in range(0, len(todo), 500):
        hits = search({"query": {"ids": {"values": [CONCEPT + x for x in todo[i:i + 500]]}},
                       "size": 1000, "_source": ["@id", LABEL]})["hits"]["hits"]
        for h in hits:
            known[h["_source"]["@id"].rsplit("/", 1)[1]] = (h["_source"].get(LABEL) or [None])[0]
    q = """PREFIX saa: <https://data.archief.amsterdam/ontology#>
PREFIX mem: <http://memorix.io/ontology#>
PREFIX dct: <http://purl.org/dc/terms/>
SELECT DISTINCT ?ag ?name WHERE { { SELECT DISTINCT ?ag WHERE { ?b saa:hasOrHadSubjectBuilding ?x ; saa:hasCreator/saa:hasAgent ?ag } }
  ?ctx mem:hasRecord ?ag ; dct:title ?name }"""
    r = requests.post(KG, data={"query": q}, headers={"Accept": "application/sparql-results+json", **UA}, timeout=600)
    for b in r.json()["results"]["bindings"]:
        known[b["ag"]["value"].removeprefix(REC)] = b["name"]["value"]
    NAMES.write_text(json.dumps(known, ensure_ascii=False))
    return known


def person(name):
    """'Schaap, C.P.' and 'C.P. Schaap' both read as 'C.P. Schaap'."""
    if not name:
        return None
    if "," in name and "(" not in name.split(",")[0]:
        last, first = name.split(",", 1)
        first = first.split("(")[0].strip()
        return f"{first} {last.strip()}".strip()
    return name.split(" (")[0].strip()


def year_of(r):
    for s in (r["begin"], r["date"]):
        if s[:4].isdigit():
            return int(s[:4])
    return None


def main():
    rows = harvest()
    print(len(rows), "images linked to buildings")
    labels = names({r["form"] for r in rows if r["form"]})
    forms = pd.Series([labels.get(r["form"]) for r in rows]).value_counts()
    print(forms.head(12).to_string())

    built = pd.read_parquet(f"{DATA}/buildings.parquet", columns=["identificatie", "year"])
    built = dict(zip(built.identificatie.str.slice(-16), built.year))

    cands = {}
    for r in rows:
        y = year_of(r)
        if not r["thumb"] or not r["panden"] or y is None:
            continue
        form = labels.get(r["form"]) or ""
        photo = form.lower().startswith("foto") or form.lower() in {"dia", "negatief", "glasnegatief"}
        maker = next((person(labels.get(a)) for a in r["agents"] if labels.get(a)), None)
        item = dict(t=r["thumb"].rsplit("/", 1)[1].removesuffix(".jpg"), r=r["id"], y=y, m=maker, k=None if photo else form)
        for p in r["panden"]:
            if p in built and y >= built[p]:
                cands.setdefault(p, []).append(((len(r["panden"]) > 3, len(r["panden"]), not photo), item))

    # Per building: the clearest picture of each decade, at most six, oldest first.
    picks = {}
    for p, cs in cands.items():
        cs.sort(key=lambda c: (c[0], -c[1]["y"]))
        if cs[0][0][0]:  # every picture shows a long row; keep only the best one
            cs = cs[:1]
        else:
            cs = [c for c in cs if not c[0][0]]
        seen, chosen = set(), []
        for _, item in cs:
            if item["y"] // 10 not in seen:
                seen.add(item["y"] // 10)
                chosen.append(item)
            if len(chosen) == PER_BUILDING:
                break
        picks[p] = sorted(chosen, key=lambda i: i["y"])
    print(len(picks), "buildings with archive pictures,", sum(map(len, picks.values())), "pictures")

    OUT.mkdir(parents=True, exist_ok=True)
    shards = [{} for _ in range(SHARDS)]
    for p, v in picks.items():
        shards[zlib.crc32(p.encode()) % SHARDS][p] = [{k: x for k, x in i.items() if x is not None} for i in v]
    for i, s in enumerate(shards):
        (OUT / f"{i:02d}.json").write_text(json.dumps(s, ensure_ascii=False, separators=(",", ":")))
    print(sum(f.stat().st_size for f in OUT.iterdir()) // 1024, "KB in", SHARDS, "shards")


if __name__ == "__main__":
    main()
