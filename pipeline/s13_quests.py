"""Resolve every quest step to its buildings and check it (web/data/quests.json).

A step is dropped, and its quest with it, when: an article lacks a checked string; a story or address is not found;
a year step's year is not the map's year for the building (within one year); a photo clue has no photo.
"""
import json
from pathlib import Path

import pandas as pd

from .quests import QUESTS
from .s08_curated import article, geocode, wikidata_bags
from .city import DATA, WEB


def main():
    b = pd.read_parquet(f"{DATA}/buildings.parquet", columns=["identificatie", "year", "date_flag", "height"])
    b["bag"] = b.identificatie.str.slice(-16)
    by = b.set_index("bag")
    curated = {L["id"]: L for L in json.load(open(f"{DATA}/curated.json"))}
    wiki = json.load(open(f"{WEB}/wiki.json"))
    wk = pd.read_parquet(f"{DATA}/wiki_index.parquet").set_index("bag").wk
    label = lambda bag, lang="en": (wiki[wk[bag]].get("label" if lang == "en" else "label_nl") if bag in wk.index else None)

    def where(at):
        kind, _, ref = at.partition(":")
        if kind == "wd":
            return sorted(wikidata_bags().get(article(ref)[1], set()))
        if kind == "story":
            layer, address = ref.split(":", 1)
            return sorted({e["bag"] for e in curated.get(layer, {}).get("entries", []) if e["address"] == address})
        if kind == "addr":
            bag, _ = geocode(ref)
            return [bag] if bag else []
        if kind == "rule" and ref == "oldest":
            exact = b[b.date_flag == 0]
            return sorted(exact[exact.year == exact.year.min()].bag)
        raise ValueError(at)

    out, problems = [], []
    for q in QUESTS:
        steps = []
        for i, s in enumerate(q["steps"]):
            here = f'{q["id"]} {i + 1}'
            bags = [x for x in where(s["at"]) if x in by.index]
            if not bags:
                problems.append(f"{here}: nothing at {s['at']}")
                continue
            missing = [(ref, c) for ref, cs in s["checks"] for c in cs if c.lower() not in article(ref)[0].lower()]
            if missing:
                problems.append(f"{here}: {missing}")
                continue
            step = {k: v for k, v in s.items() if k not in ("checks", "at") and v is not None}
            step["bags"] = bags
            step["sources"] = sorted({article(ref)[1] for ref, _ in s["checks"]})
            if s["at"].startswith("story:"):
                layer, address = s["at"][6:].split(":", 1)
                e = next(e for e in curated[layer]["entries"] if e["address"] == address)
                step["sources"] = sorted(set(step["sources"]) | {e["source"]})
            if s["kind"] == "year":
                years = sorted({int(by.loc[x, "year"]) for x in bags})
                if not any(abs(y - s["year"]) <= 1 for y in years):
                    problems.append(f"{here}: map says {years}, step says {s['year']}")
                    continue
            if s.get("clue") == "today":
                img = next((wiki[wk[x]]["image"] for x in bags if x in wk.index and wiki[wk[x]].get("image")), None)
                if not img:
                    problems.append(f"{here}: no photo")
                    continue
                step["clue"] = dict(thumb=img["thumb"], page=img.get("page"), artist=img.get("artist"),
                                    license=img.get("license"))
            steps.append(step)
        if len(steps) == len(q["steps"]):
            out.append(dict({k: v for k, v in q.items() if k != "steps"}, steps=steps))
        print(f'{q["id"]:10s} level {q["level"]}  {len(steps)}/{len(q["steps"])}')
    for p in problems:
        print("problem:", p)
    Path(f"{WEB}/quests.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(len(out), "quests")


if __name__ == "__main__":
    main()
