"""Fetch the city's archaeology from the RCE (CC0): what lies under the buildings, for the viewer's archaeology mode.

From the Elastic projection (rce.py), openbaar records only:
  raw/archeo/areas.json     onderzoeksgebieden of the municipality: [{id, nr, wkt, registered}]
  raw/archeo/spots.json     vondstlocaties: [{id, area, name, how, note}] (their geometry is their area's)
  raw/archeo/objects.json   what the areas hold: archeologische complexen, grondsporen and vondsten,
                            [{id, kind, area, spot, type, typeUri, material, materialUri, begin, end, beginLabel,
                              endLabel, n}] with begin/end in years (negative before Christ)
  raw/archeo/terrains.json  archaeological rijksmonumenten (protected sites): [{id, nr, name, txt, wkt}]
From the Referentienetwerk (RN2, SPARQL):
  raw/archeo/periods.json   the ABR periods with their years, code and broader period
  raw/archeo/terms.json     label and broader term of every type and material used
"""
import json
from pathlib import Path

from . import rce
from .city import CFG, DATA, LABEL, UA

GEMEENTE = CFG.get("gemeentenaam", LABEL)
OUT = Path(f"{DATA}/raw/archeo")
F = rce.F
WKT = "http://www opengis net/ont/geosparql#asWKT"
KINDS = ["archeologischcomplex", "grondsporen", "vondsten"]


def first(s, k, cast=str):
    v = s.get(F + k) or []
    return cast(v[0]) if v else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    in_city = {"term": {F + "gemeente.keyword": GEMEENTE}}
    public = lambda s: (s.get(F + "vertrouwelijk") or ["openbaar"])[0] == "openbaar"

    docs = rce.elastic_all([{"term": {"@id.soort": "archeologischonderzoeksgebied"}}, in_city], UA,
                           ["cultuurhistorischObjectnummer", "registratiedatum", "vertrouwelijk", WKT])
    areas = [dict(id=s["@id"], nr=first(s, "cultuurhistorischObjectnummer"), wkt=s[WKT][0],
                  registered=first(s, "registratiedatum")) for s in docs if public(s) and s.get(WKT)]
    print(len(docs), "onderzoeksgebieden,", len(areas), "openbaar with an outline")
    ids = {a["id"] for a in areas}

    docs = rce.elastic_all([{"term": {"@id.soort": "vondstlocatie"}}, in_city], UA,
                           ["ligtInObject", "locatienaam", "verwerving", "overigeOmschrijving", "omschrijving", "vertrouwelijk"])
    spots = [dict(id=s["@id"], area=first(s, "ligtInObject"), name=first(s, "locatienaam"),
                  how=first(s, "verwerving"), note=first(s, "omschrijving") or first(s, "overigeOmschrijving"))
             for s in docs if public(s) and first(s, "ligtInObject") in ids]
    print(len(docs), "vondstlocaties,", len(spots), "openbaar in those areas")

    objects, area_ids = [], sorted(ids)
    for kind in KINDS:
        n = 0
        for i in range(0, len(area_ids), 150):
            docs = rce.elastic_all([{"term": {"@id.soort": kind}}, {"terms": {F + "onderzoeksgebied": area_ids[i:i + 150]}}], UA,
                                   ["onderzoeksgebied", "ligtInObject", "type", "heeftTypeNaam", "materiaal", "heeftMateriaalNaam",
                                    "beginjaar", "eindjaar", "beginperiode", "eindperiode", "aantalVondsten", "vertrouwelijk"])
            for s in docs:
                if not public(s):
                    continue
                objects.append(dict(id=s["@id"], kind=kind, area=first(s, "onderzoeksgebied"), spot=first(s, "ligtInObject"),
                                    type=first(s, "type"), typeUri=first(s, "heeftTypeNaam"),
                                    material=first(s, "materiaal"), materialUri=first(s, "heeftMateriaalNaam"),
                                    begin=first(s, "beginjaar", int), end=first(s, "eindjaar", int),
                                    beginLabel=first(s, "beginperiode"), endLabel=first(s, "eindperiode"),
                                    n=first(s, "aantalVondsten", int)))
                n += 1
        print(kind, n)

    docs = rce.elastic_all([{"term": {"@id.soort": "rijksmonument"}}, in_city,
                            {"term": {F + "monumentAard.keyword": "archeologisch"}},
                            {"term": {F + "juridischeStatus.keyword": "rijksmonument"}}], UA,
                           ["rijksmonumentnummer", "naam", "locatieomschrijving", "omschrijving", WKT])
    terrains = [dict(id=s["@id"], nr=first(s, "rijksmonumentnummer"), name=first(s, "naam") or first(s, "locatieomschrijving"),
                     txt=" ".join((first(s, "omschrijving") or "").split()), wkt=s[WKT][0]) for s in docs if s.get(WKT)]
    print(len(terrains), "archaeological rijksmonumenten")

    periods = rce.abr_periods(UA)
    used = sorted({o[k] for o in objects for k in ("typeUri", "materialUri") if o[k]})
    t = rce.terms(used, UA)
    print(len(periods), "ABR periods,", len(t), "of", len(used), "terms resolved")

    for name, data in (("areas", areas), ("spots", spots), ("objects", objects), ("terrains", terrains),
                       ("periods", periods), ("terms", t)):
        (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
