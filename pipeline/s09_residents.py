"""Well-known residents: people whose Dutch Wikipedia article names the Amsterdam address they lived or worked at.

1. Wikidata: people tied to Amsterdam (born, died, lived or worked there) with a Dutch Wikipedia article.
2. Their article's wikitext is searched for an Amsterdam street name followed by a house number, in a
   sentence about living, moving, dying or working there.
3. The address is geocoded to a BAG building (PDOK Locatieserver, Amsterdam only, exact house number).
The sentence is kept as the source quote; house numbers can have changed since the person lived there.
"""
import json
from concurrent.futures import ThreadPoolExecutor
import re
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import Point
from .city import DATA, WEB

UA = {"User-Agent": "amsterdam-by-building/0.1 (https://stop-token.com/lab/amsterdam/)"}
VERBS = re.compile(r"\b(woonde|woonden|woont|bewoonde|verhuisde|betrok|vestigde|kocht|overleed|stierf|geboren|"
                   r"atelier|werkte|huis aan|woning aan|woonhuis|pand aan|leefde|groeide op|woonachtig|"
                   r"in het pand|in het huis|geboortehuis|sterfhuis|op nummer)\b", re.I)
SELF = re.compile(r"\b(hij|zij|ze|het gezin|het echtpaar|de familie|het paar)\b", re.I)


def people():
    q = """SELECT ?p ?pLabel ?article ?desc ?born ?died ?img (MAX(?sl) AS ?links) WHERE {
      VALUES ?prop { wdt:P19 wdt:P20 wdt:P551 wdt:P937 }
      ?p ?prop wd:Q727 ; wdt:P31 wd:Q5 ; wikibase:sitelinks ?sl .
      FILTER(?sl >= 3)
      ?article schema:about ?p ; schema:isPartOf <https://nl.wikipedia.org/> .
      OPTIONAL { ?p schema:description ?desc FILTER(lang(?desc)="en") }
      OPTIONAL { ?p wdt:P569 ?born } OPTIONAL { ?p wdt:P570 ?died } OPTIONAL { ?p wdt:P18 ?img }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en,nl". }
    } GROUP BY ?p ?pLabel ?article ?desc ?born ?died ?img"""
    r = requests.get("https://query.wikidata.org/sparql", params={"query": q, "format": "json"}, headers=UA, timeout=300)
    out = {}
    for b in r.json()["results"]["bindings"]:
        v = {k: x["value"] for k, x in b.items()}
        out.setdefault(v["p"], v)
    return list(out.values())


def street_hits(streets):
    """Dutch Wikipedia articles whose source has '<street> <number>', found with a regex search per street."""
    cache = Path(f"{DATA}/raw/nlwiki_street_hits.json")
    hits = json.loads(cache.read_text()) if cache.exists() else {}
    def one(st):
        titles, offset = [], 0
        while offset is not None:
            for attempt in range(5):
                r = requests.get("https://nl.wikipedia.org/w/api.php", headers=UA, timeout=120, params={
                    "action": "query", "list": "search", "format": "json", "srlimit": 500, "srprop": "",
                    "sroffset": offset, "srnamespace": 0, "srsearch": f'insource:/{st} [0-9]/'})
                if r.ok and "query" in r.json():
                    break
                time.sleep(3 * 2 ** attempt)
            d = r.json()
            titles += [x["title"] for x in d.get("query", {}).get("search", [])]
            offset = d.get("continue", {}).get("sroffset")
            time.sleep(0.5)
        return st, titles

    todo = [st for st in streets if st not in hits]
    with ThreadPoolExecutor(3) as ex:
        for i, (st, titles) in enumerate(ex.map(one, todo)):
            hits[st] = titles
            if i % 20 == 0:
                cache.write_text(json.dumps(hits, ensure_ascii=False))
    cache.write_text(json.dumps(hits, ensure_ascii=False))
    return hits


def humans(titles):
    """Keep the titles whose Wikidata item is a person, with the same fields people() returns."""
    out = []
    for i in range(0, len(titles), 200):
        vals = " ".join(f'<https://nl.wikipedia.org/wiki/{requests.utils.quote(t.replace(" ", "_"), safe="")}>' for t in titles[i:i + 200])
        q = f"""SELECT ?p ?pLabel ?article ?desc ?born ?died ?img (MAX(?sl) AS ?links) WHERE {{
          VALUES ?article {{ {vals} }} ?article schema:about ?p . ?p wdt:P31 wd:Q5 ; wikibase:sitelinks ?sl .
          OPTIONAL {{ ?p schema:description ?desc FILTER(lang(?desc)="en") }}
          OPTIONAL {{ ?p wdt:P569 ?born }} OPTIONAL {{ ?p wdt:P570 ?died }} OPTIONAL {{ ?p wdt:P18 ?img }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,nl". }}
        }} GROUP BY ?p ?pLabel ?article ?desc ?born ?died ?img"""
        r = requests.post("https://query.wikidata.org/sparql", data={"query": q, "format": "json"}, headers=UA, timeout=300)
        seen = set()
        for b in r.json()["results"]["bindings"]:
            v = {k: x["value"] for k, x in b.items()}
            if v["p"] not in seen:
                seen.add(v["p"]); out.append(v)
        time.sleep(1)
    return out


def wikitexts(titles):
    texts = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        for attempt in range(5):
            r = requests.get("https://nl.wikipedia.org/w/api.php", headers=UA, timeout=120, params={
                "action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "format": "json",
                "formatversion": 2, "redirects": 1, "titles": "|".join(chunk)})
            if r.ok and r.headers.get("content-type", "").startswith("application/json"):
                break
            time.sleep(2 ** attempt)
        d = r.json()["query"]
        back = {n["to"]: n["from"] for n in d.get("normalized", []) + d.get("redirects", [])}
        for p in d["pages"]:
            t = p["title"]
            while t in back:
                t = back[t]
            if p.get("revisions"):
                texts[t] = p["revisions"][0]["slots"]["main"]["content"]
        time.sleep(0.3)
    return texts


BUILDING_ARTICLES = {}  # nl Wikipedia title → BAG ids of the building the article is about (Wikidata P5208)


def building_articles():
    import csv
    for r in csv.DictReader(open(f"{DATA}/raw/wd_buildings.csv")):
        if r["nl"]:
            t = requests.utils.unquote(r["nl"].rsplit("/wiki/", 1)[1]).replace("_", " ")
            BUILDING_ARTICLES.setdefault(t, set()).add(r["bag"].zfill(16))


def mark_buildings(wt):
    """Links to building articles become ⟦title⟧ markers, so a sentence can point at a building by name
    (the Rembrandthuis) as well as by address."""
    def repl(m):
        title = m.group(1).strip()
        title = title[:1].upper() + title[1:]
        text = m.group(2) or m.group(1)
        return f"⟦{title}⟧{text}" if title in BUILDING_ARTICLES else m.group(0)
    return re.sub(r"\[\[([^|\]#]+)(?:\|([^\]]*))?\]\]", repl, wt)


def clean(wt):
    """Wikitext to plain sentences; headings become sentence breaks so a quote never spans sections."""
    wt = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>|<!--.*?-->", "", wt, flags=re.S)
    for _ in range(3):
        wt = re.sub(r"\{\{[^{}]*\}\}", "", wt)
    wt = re.sub(r"\[\[(?:Bestand|File|Afbeelding|Categorie|Image):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", "", wt, flags=re.I)
    wt = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", wt)
    wt = re.sub(r"\[https?://\S+\s*([^\]]*)\]", r"\1", wt)
    wt = re.sub(r"^=+[^=\n]*=+\s*$", ". ", wt, flags=re.M)
    wt = re.sub(r"^[*#:;|!{].*$", ". ", wt, flags=re.M)
    wt = re.sub(r"<[^>]+>|'{2,}|thumb\|", "", wt)
    return re.sub(r"\s+", " ", wt)


GEO = {}


def geocode(address, buildings):
    if address in GEO:
        return GEO[address]
    r = requests.get("https://api.pdok.nl/bzk/locatieserver/search/v3_1/free", headers=UA, timeout=60, params={
        "q": address, "fq": ["type:adres", "woonplaatsnaam:Amsterdam"], "rows": 5, "fl": "weergavenaam,centroide_rd"}).json()
    exact = re.compile(re.escape(address) + r"(?:[A-Za-z]|-\w+)?,", re.I)
    docs = [d for d in r["response"]["docs"] if exact.match(d["weergavenaam"])]
    bag = None
    if docs:
        x, y = map(float, docs[0]["centroide_rd"][6:-1].split())
        hit = buildings[buildings.contains(Point(x, y))]
        bag = hit.bag.iloc[0] if not hit.empty else None
    GEO[address] = bag
    return bag


def main():
    building_articles()
    ppl = people()
    labels = json.load(open(f"{WEB}/labels.json"))
    # Streets worth a search: the named canals and main streets, and every street within 2.5 km of the Dam.
    near = sorted({l["name"] for l in labels if len(l["name"]) > 4 and
                   (l["tier"] == 1 or min(x * x + z * z for x, z, *_ in l["pts"]) < 2500 ** 2)})
    hits = street_hits(near)
    extra = sorted({t for ts in hits.values() for t in ts})
    known = {requests.utils.unquote(p["article"].rsplit("/wiki/", 1)[1]).replace("_", " ") for p in ppl}
    ppl += humans([t for t in extra if t not in known])
    print(len(ppl), "people,", len(near), "streets searched")
    titles = sorted({requests.utils.unquote(p["article"].rsplit("/wiki/", 1)[1]).replace("_", " ") for p in ppl})
    texts = wikitexts(titles)
    print(len(texts), "articles")
    streets = sorted({l["name"] for l in json.load(open(f"{WEB}/labels.json")) if len(l["name"]) > 4}, key=len, reverse=True)
    addr_re = re.compile(r"\b(" + "|".join(map(re.escape, streets)) + r")\s+(\d{1,4}[a-z]?)\b")
    b = gpd.read_parquet(f"{DATA}/buildings.parquet", columns=["identificatie", "geometry"])
    b["bag"] = b.identificatie.str.slice(-16)

    found = []
    for p in ppl:
        title = requests.utils.unquote(p["article"].rsplit("/wiki/", 1)[1]).replace("_", " ")
        text = clean(mark_buildings(texts.get(title, "")))
        seen = set()
        surname = p["pLabel"].split()[-1].lower()
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text):
            if not VERBS.search(sentence) or len(sentence) > 400:
                continue
            # The sentence must be about this person: their surname, or a pronoun opening it.
            if surname not in sentence.lower() and not SELF.match(sentence.strip()):
                continue
            quote = re.sub(r"⟦[^⟧]*⟧", "", sentence).strip()[:400]
            # a church named in a sentence about a burial is where they lie, not where they lived
            buried = re.search(r"\b(begraven|bijgezet|begraafplaats|graf|grafkelder)\b", sentence, re.I)
            for t in ([] if buried else re.findall(r"⟦([^⟧]*)⟧", sentence)):
                for bag in BUILDING_ARTICLES[t]:
                    if ("article", bag) not in seen:
                        seen.add(("article", bag))
                        found.append(dict(bag=bag, address=t, person=p["pLabel"], wikidata=p["p"], url=p["article"],
                                          desc=p.get("desc"), born=(p.get("born") or "")[:4], died=(p.get("died") or "")[:4],
                                          img=p.get("img"), links=int(p["links"]), quote=quote))
            for m in re.finditer(addr_re, re.sub(r"⟦[^⟧]*⟧", "", sentence)):
                address = f"{m.group(1)} {m.group(2)}"
                if address in seen:
                    continue
                seen.add(address)
                bag = geocode(address, b)
                if bag:
                    found.append(dict(bag=bag, address=address, person=p["pLabel"], wikidata=p["p"],
                                      url=p["article"], desc=p.get("desc"), born=(p.get("born") or "")[:4],
                                      died=(p.get("died") or "")[:4], img=p.get("img"),
                                      links=int(p["links"]), quote=quote))
    import csv
    for r in csv.DictReader(open(f"{DATA}/raw/wd_residents.csv")):
        why = {"P551": "Wikidata records this building as their residence.",
               "P937": "Wikidata records this building as their place of work.",
               "P19": "Wikidata records this building as their birthplace.",
               "P20": "Wikidata records this building as the place where they died."}[r["prop"].rsplit("/", 1)[1]]
        found.append(dict(bag=r["bag"].zfill(16), address="", person=r["personLabel"], wikidata=r["person"],
                          url=r["person"], desc=r["desc"], born=r["born"][:4], died=r["died"][:4], img=r["img"],
                          links=0, quote=why))
    uniq = {}
    for f in found:  # one entry per person and building; Wikipedia quotes come first, so they win
        uniq.setdefault((f["bag"], f["person"]), f)
    found = sorted(uniq.values(), key=lambda f: -f["links"])
    Path(f"{DATA}/residents.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))
    print(len(found), "addresses;", len({f["person"] for f in found}), "people;", len({f["bag"] for f in found}), "buildings")


if __name__ == "__main__":
    main()
