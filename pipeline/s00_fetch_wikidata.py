"""Buildings and monuments of the city on Wikidata (CC0), by their BAG pand id (P5208): the inputs of s06_wiki.

raw/wd_buildings.csv  i, bag, labelEn, labelNl, en, nl, image, architects, styles (| separated): names, articles
                      and photos for the building cards
raw/wd_monuments.csv  nr, bag, inception, label: rijksmonuments (P359) with their pand, for monuments.py
A pand id starts with the code of the municipality that registered it, which selects the city's buildings.
"""
import csv
import time

import requests

from .city import DATA, GEMEENTE_CODE, UA

WDQS = "https://query.wikidata.org/sparql"

BUILDINGS = """SELECT ?i ?bag ?labelEn ?labelNl ?en ?nl (SAMPLE(?img) AS ?image)
  (GROUP_CONCAT(DISTINCT ?archL; separator="|") AS ?architects) (GROUP_CONCAT(DISTINCT ?styleL; separator="|") AS ?styles)
WHERE {
  ?i wdt:P5208 ?bag . FILTER(STRSTARTS(?bag, "%(code)s"))
  OPTIONAL { ?i rdfs:label ?labelEn FILTER(LANG(?labelEn) = "en") }
  OPTIONAL { ?i rdfs:label ?labelNl FILTER(LANG(?labelNl) = "nl") }
  OPTIONAL { ?en schema:about ?i ; schema:isPartOf <https://en.wikipedia.org/> }
  OPTIONAL { ?nl schema:about ?i ; schema:isPartOf <https://nl.wikipedia.org/> }
  OPTIONAL { ?i wdt:P18 ?img }
  OPTIONAL { ?i wdt:P84 ?a . ?a rdfs:label ?archL FILTER(LANG(?archL) = "nl") }
  OPTIONAL { ?i wdt:P149 ?s . ?s rdfs:label ?styleL FILTER(LANG(?styleL) = "nl") }
} GROUP BY ?i ?bag ?labelEn ?labelNl ?en ?nl"""

MONUMENTS = """SELECT ?nr ?bag (MIN(?inc) AS ?inception) (SAMPLE(?l) AS ?label) WHERE {
  ?i wdt:P359 ?nr ; wdt:P5208 ?bag . FILTER(STRSTARTS(?bag, "%(code)s"))
  OPTIONAL { ?i wdt:P571 ?inc }
  OPTIONAL { ?i rdfs:label ?l FILTER(LANG(?l) = "nl") }
} GROUP BY ?nr ?bag"""


def query(q: str) -> list[dict]:
    for attempt in range(5):
        r = requests.post(WDQS, data={"query": q % {"code": GEMEENTE_CODE}}, timeout=300,
                          headers={"Accept": "application/sparql-results+json", **UA})
        if r.ok:
            return [{k: v["value"] for k, v in b.items()} for b in r.json()["results"]["bindings"]]
        time.sleep(10 * (attempt + 1))
    r.raise_for_status()


def write(name: str, rows: list[dict], cols: list[str]):
    with open(f"{DATA}/raw/{name}", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in cols} for r in rows)
    print(name, len(rows))


def main():
    write("wd_buildings.csv", query(BUILDINGS), ["i", "bag", "labelEn", "labelNl", "en", "nl", "image", "architects", "styles"])
    write("wd_monuments.csv", query(MONUMENTS), ["nr", "bag", "inception", "label"])


if __name__ == "__main__":
    main()
