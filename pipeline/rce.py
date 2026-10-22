"""The national monument register (RCE, CC0): its Elasticsearch projection first, its SPARQL endpoint for the rest.

Two ways into the same data, the CHO knowledge graph modelled on the CEO ontology
(https://linkeddata.cultureelerfgoed.nl/def/ceo):

- Elastic: the search projection of github.com/jolietjakeblues/elastic-ceo, one flat document per heritage object
  (service Erfgoed-ceo on dataset rce/erfgoed). One request returns a municipality's monuments with their
  description, style, function, building years (beginjaar, eindjaar) and BAG verblijfsobjecten. Still an experiment:
  when it fails, the SPARQL queries below give the same files, without the building years.
- SPARQL (rce/cho): the only route to ceo:heeftPand, the BAG pand a monument stands on, which the projection leaves
  out. The queries were worked out with the RCE MCP server, which wraps this endpoint; the pipeline calls the endpoint
  itself because the MCP caps results at 100 rows.

What the endpoint teaches:
- A monument names its municipality and its BAG objects on its basisregistratie relation: ceo:heeftBasisregistratieRelatie
  / ceo:gemeentenaam, and / ceo:heeftBAGRelatie / ceo:heeftPand or ceo:heeftVerblijfsobject. Most relations give only
  the verblijfsobject (Amersfoort: 170 panden, 735 verblijfsobjecten): its pand comes from BAG (s00_fetch_addresses).
- Triples come back several times (one object sits in several graphs): select DISTINCT, and dedupe.
- A monument has up to two descriptions; the register's own has ceo:heeftOmschrijvingstype 'rijksmonumentomschrijving',
  the other lists literature, whose years date the books.
- Spatial filters (geof:sfWithin) time out: protected townscapes come as WKT (WGS84) and are cut locally.
- Heavy queries answer 504: one kind of fact per query, paged with LIMIT/OFFSET.
"""
import time

import requests

ENDPOINT = "https://api.linkeddata.cultureelerfgoed.nl/datasets/rce/cho/services/cho/sparql"
ELASTIC = "https://api.linkeddata.cultureelerfgoed.nl/datasets/rce/erfgoed/services/Erfgoed-ceo/_search"
F = "https://linkeddata cultureelerfgoed nl/def/ceo-elastic#"  # field prefix: Triply turns the dots into spaces
PREFIXES = """PREFIX ceo: <https://linkeddata.cultureelerfgoed.nl/def/ceo#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
"""
PAGE = 5000
PAND = "http://bag.basisregistraties.overheid.nl/bag/id/pand/"
VBO = "http://bag.basisregistraties.overheid.nl/bag/id/verblijfsobject/"
RIJKSMONUMENT = "https://data.cultureelerfgoed.nl/term/id/rn/2/b2d9a59a-fe1e-4552-9a05-3c2acddff864"
OMSCHRIJVING = "https://data.cultureelerfgoed.nl/term/id/rn/2/0273a12d-7259-4391-aee2-5dac264aebe9"


def monument(nr, name=None, function=None, styles=(), years=None, txt=None, vbos=(), panden=()):
    """One monument as the pipeline keeps it, whichever route it came by."""
    return dict(nr=str(nr), status="Rijksmonument", name=name, function=function, styles=list(styles), years=years,
                txt=txt, vbos=sorted(set(vbos)), panden=sorted(set(panden)), address=None, architect=None)


# ---------- Elastic ----------

def from_elastic(gemeente: str, ua: dict) -> list[dict]:
    """Every rijksmonument of a municipality from the Erfgoed-ceo projection, in one request."""
    body = {"size": 10000, "track_total_hits": True, "query": {"bool": {"filter": [
        {"term": {"@id.soort": "rijksmonument"}},
        {"term": {F + "gemeente.keyword": gemeente}},
        {"term": {F + "juridischeStatus.keyword": "rijksmonument"}}]}}}
    r = requests.post(ELASTIC, json=body, headers=ua, timeout=120)
    r.raise_for_status()
    d = r.json()
    assert d["hits"]["total"]["value"] == len(d["hits"]["hits"]) < 10000, "page the request"
    out = []
    for h in d["hits"]["hits"]:
        s = h["_source"]
        get = lambda k: s.get(F + k) or []
        begin, end = get("beginjaar"), get("eindjaar")
        # Building years only when the record names one event: the projection is flat, so with two events
        # (building and rebuilding) it no longer says which year belongs to which.
        years = (int(begin[0]), int((end or begin)[0])) if len(begin) == 1 and len(end) <= 1 else None
        out.append(monument(get("rijksmonumentnummer")[0], name=(get("naam") or [None])[0],
                            function=(get("oorspronkelijkeFunctie") or get("functie") or [None])[0],
                            styles=[s for s in get("stijl") if s != "n.v.t."], years=years, txt=" ".join((get("omschrijving") or [""])[0].split()),
                            vbos=get("verblijfsobjectIdentificatie")))
    return out


# ---------- SPARQL ----------

def select(body: str, ua: dict) -> list[dict]:
    """Run a SELECT, page by page, and return its rows as {variable: value}."""
    rows, offset = [], 0
    while True:
        q = f"{PREFIXES}{body}\nLIMIT {PAGE} OFFSET {offset}"
        for attempt in range(5):
            r = requests.post(ENDPOINT, data={"query": q}, timeout=300,
                              headers={"Accept": "application/sparql-results+json", **ua})
            if r.ok:
                break
            if attempt == 4:
                r.raise_for_status()
            time.sleep(5 * (attempt + 1))
        page = [{k: v["value"] for k, v in b.items()} for b in r.json()["results"]["bindings"]]
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


def in_municipality(gemeente: str) -> str:
    """Graph pattern binding ?m and ?nr to every current rijksmonument of a municipality."""
    return f"""?br ceo:gemeentenaam "{gemeente}" .
  ?m ceo:heeftBasisregistratieRelatie ?br ; ceo:rijksmonumentnummer ?nr ;
     ceo:heeftJuridischeStatus <{RIJKSMONUMENT}> ."""


def bag_links(gemeente: str, ua: dict) -> dict[str, tuple[set, set]]:
    """{monument nr: (panden, verblijfsobjecten)}, the 16-digit BAG ids the register links the monument to."""
    rows = select(f"""SELECT DISTINCT ?nr ?pand ?vbo WHERE {{ {in_municipality(gemeente)}
  ?m ceo:heeftBasisregistratieRelatie/ceo:heeftBAGRelatie ?bag .
  OPTIONAL {{ ?bag ceo:heeftPand ?pand }} OPTIONAL {{ ?bag ceo:heeftVerblijfsobject ?vbo }} }}""", ua)
    out = {}
    for r in rows:
        panden, vbos = out.setdefault(r["nr"], (set(), set()))
        if "pand" in r:
            panden.add(r["pand"].removeprefix(PAND))
        if "vbo" in r:
            vbos.add(r["vbo"].removeprefix(VBO))
    return out


def from_sparql(gemeente: str, ua: dict) -> list[dict]:
    """The same monuments as from_elastic, by SPARQL, without building years."""
    m = in_municipality(gemeente)
    first = lambda rows, key: {r["nr"]: r[key] for r in sorted(rows, key=lambda r: r[key], reverse=True)}
    names = first(select(f"SELECT DISTINCT ?nr ?naam WHERE {{ {m} ?m ceo:heeftNaam/ceo:naam ?naam }}", ua), "naam")
    funcs = first(select(f"""SELECT DISTINCT ?nr (STR(?l) AS ?function) WHERE {{ {m}
  ?m ceo:heeftOorspronkelijkeFunctie/ceo:heeftFunctieNaam/skos:prefLabel ?l FILTER(lang(?l) = "nl") }}""", ua), "function")
    texts = first(select(f"""SELECT DISTINCT ?nr ?txt WHERE {{ {m}
  ?m ceo:heeftOmschrijving ?o . ?o ceo:heeftOmschrijvingstype <{OMSCHRIJVING}> ; ceo:omschrijving ?txt }}""", ua), "txt")
    styles = {}
    for r in select(f"""SELECT DISTINCT ?nr (STR(?l) AS ?style) WHERE {{ {m}
  ?m ceo:heeftStijlEnCultuur/ceo:heeftStijlEnCultuurNaam/skos:prefLabel ?l FILTER(STR(?l) != "n.v.t.") }}""", ua):
        styles.setdefault(r["nr"], []).append(r["style"])
    nrs = [r["nr"] for r in select(f"SELECT DISTINCT ?nr WHERE {{ {m} }}", ua)]
    return [monument(nr, name=names.get(nr), function=funcs.get(nr), styles=styles.get(nr, ()),
                     txt=" ".join(texts.get(nr, "").split())) for nr in nrs]


def actors(gemeente: str, ua: dict) -> list[dict]:
    """Who made each monument, with their role: architect, garden architect, sculptor, client (opdrachtgever), ...

    ceo:heeftGebeurtenis / ceo:heeftActorEnRol pairs an actor (a term with a label such as 'Kroes, H. ; Stad
    Amersfoort') with a role. The Elastic projection flattens the two into separate lists, so this comes by SPARQL.
    """
    rows = select(f"""SELECT DISTINCT ?nr ?actor (STR(?al) AS ?name) (STR(?rl) AS ?role) WHERE {{ {in_municipality(gemeente)}
  ?m ceo:heeftGebeurtenis/ceo:heeftActorEnRol ?ar .
  ?ar ceo:heeftActor ?actor . FILTER(isIRI(?actor))
  ?actor skos:prefLabel ?al .
  OPTIONAL {{ ?ar ceo:heeftRol/skos:prefLabel ?rl }} }}""", ua)
    return [dict(nr=r["nr"], actor=r["actor"], name=r["name"], role=r.get("role")) for r in rows]


def townscapes(ua: dict) -> list[dict]:
    """All protected town and village views (beschermde stads- en dorpsgezichten) in the country, WKT in WGS84."""
    rows = select("""SELECT DISTINCT ?nr ?naam (STR(?sl) AS ?status) ?wkt WHERE {
  ?g a ceo:Gezicht ; ceo:gezichtsnummer ?nr ; ceo:heeftGeometrie/geo:asWKT ?wkt .
  OPTIONAL { ?g ceo:heeftNaam/ceo:naam ?naam }
  OPTIONAL { ?g ceo:heeftGezichtsstatus/skos:prefLabel ?sl } }""", ua)
    out = {}
    for r in rows:
        out.setdefault(r["nr"], r)
    return list(out.values())
