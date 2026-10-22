# LAYRS: a Dutch city, building by building

Every building standing in a Dutch municipality today, in 3D, coloured by the year it was built and set in its
history, from national open data only. Live:

- Amersfoort: https://layrs-amersfoort.pages.dev
- Maastricht: https://layrs-maastricht.pages.dev
- Dordrecht: https://layrs-dordrecht.pages.dev
- Gouda: https://www.goudatijdmachine.nl/layrs/ (hosted by the Gouda Tijdmachine, see [Gouda](#gouda))

A non-commercial test. It grew out of Alex Barakov's
[Amsterdam, building by building](https://github.com/alexbarakov/amsterdam-by-building) (MIT), itself inspired by
Sasha Bogachev's [Paris, building by building](https://paris.bogachev.fr); the viewer and the tile format are his.

## How it works

```
national open data ──► pipeline/ (Python) ──► web/data/<city>/ (binary tiles + JSON) ──► web/ (three.js, no build step)
```

Every city has a config in [`cities/`](cities/): its municipality code, the centre of its old town, its periods, the
main streets to label from afar, and the pipeline steps. The pipeline reads and writes `data/<city>/` and
`web/data/<city>/`.

| Step | Source | What it gives |
|---|---|---|
| `s00_fetch_boundary` | PDOK Bestuurlijke Gebieden | the municipality's outline |
| `s00_fetch_3dbag`, `s00_fetch_3dbv` | 3D BAG (TU Delft), or else Kadaster's 3D Basisvoorziening | buildings, heights, years; the fallback has no roof shapes |
| `s00_fetch_water`, `s00_fetch_addresses` | BGT and BAG via PDOK | water, every address with its building |
| `s00_fetch_energy` | RVO via RIVM Atlas Leefomgeving | energy labels |
| `s00_fetch_rce` ([`rce.py`](pipeline/rce.py)) | RCE monument register: its Elastic projection ([elastic-ceo](https://github.com/jolietjakeblues/elastic-ceo)), then SPARQL | monuments on their BAG panden, descriptions, styles, building years, makers and clients, complexes, photos from the RCE image bank, protected townscapes |
| `s00_fetch_wikidata` | Wikidata | names, articles, photos and architects, by BAG pand id and by monument number |
| `s01_load`, `s02_attributes` | | buildings and parts; years cleaned: placeholders, rounded years, the register's earlier dates |
| `s01c_roofs`, `s01d_spires` | 3D BAG LoD 2.2, AHN | roofs, towers and spires (3D BAG only) |
| `s05_layers` ([`layers.py`](pipeline/layers.py)) | | the context layers: monuments by function (each with a line from the register, the stops of a walk), gables, styles, complexes, protected townscapes, protected heritage |
| `s07_labels` | Nationaal Wegenbestand | street names along their streets |
| `s10_commons`, `s06_wiki` | Wikimedia Commons, Wikipedia | photos (also by address or monument number in the file name), article extracts, the city's own article |
| `s03_tiles`, `s04_water` | | 600 m tiles in 8 packs, per-building attributes, water and land |
| `s13_graph` | | makers, clients, complexes and styles of the monuments, linked to their buildings; architects with their Wikipedia article |
| `s14_search`, `s15_addresses` | | search index, an address per building |
| `s16_register` | | the register's entry per monument for the building card: text, complex, RCE photos |
| `s00_fetch_archeo`, `s17_archeo` | RCE Elastic projection and Referentienetwerk (ABR) | archaeology mode (optional, Amersfoort): research areas under the city, one layer per ABR period, the deeper the older; archeologische complexen, grondsporen, vondsten; protected sites; a graph of ABR terms |

## Run it

Plain Python 3.12 or newer, no virtual environment:

```bash
python -m pip install -r requirements.txt
python -m pipeline.run amersfoort                 # every step; or: ... amersfoort s05 s03, or --from s02
python -m http.server 8642 --directory web        # http://localhost:8642/?city=amersfoort
.\scripts\deploy.ps1 amersfoort                   # dist/amersfoort/ onto Cloudflare Pages, project layrs-amersfoort
```

Raw downloads (`data/`), generated output (`web/data/`) and built sites (`dist/`) are not in the repository: they are
large and rebuilt by the pipeline.

## Another city

Copy a file in `cities/`, set `label`, `gemeentecode` (the four digits BAG ids start with), `origin` (RD New),
`starts`, `home`, `periods` and `tier1`, and run the pipeline with its name. The register's name for the municipality
is `label`, or `gemeentenaam` when it differs. When the city's Wikipedia article is not titled `label`, name it
with `wikipedia` (`{"nl": ..., "en": ...}`). See [CONTRIBUTING.md](CONTRIBUTING.md).

## Gouda

[`cities/gouda.json`](cities/gouda.json) is configuration only, like the other cities. Its periods and main streets
are a first draft, still to be checked by the Gouda Tijdmachine. Gouda is not on Cloudflare Pages: the pipeline runs
on the Gouda Tijdmachine's server in a virtual environment, and Apache serves the built site through a symlink:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pipeline.run gouda
.venv/bin/python scripts/build_site.py gouda     # dist/gouda/; the _headers file there is for Cloudflare only
# once: ln -s <repo>/dist/gouda <www.goudatijdmachine.nl document root>/layrs
```

Roadmap:

- [ ] Periods and `tier1` streets checked by the Gouda Tijdmachine
- [ ] Roofs and spires: the first build (2026-10-22) could not reach data.3dbag.nl and fell back to the 3D
  Basisvoorziening, so it has no LoD 2.2 roofs; rerun with `--from s00_fetch_3dbag` once 3D BAG answers again
- [ ] A Gouda Tijdmachine layer: stories and photos per building from its own linked data (licence to check first)
- [ ] Long cache headers for the `.bin` tiles on Apache

## Data decisions

- **Years.** BAG gives every building a construction year but not always a true one: placeholders (1005) are estimated
  from dated neighbours, and round years before 1800 are spread across their rounding step. Where the monument
  register dates a building earlier than BAG, which often records a rebuilding, the register wins: its building years
  where it records them as data, else the first date in its description.
- **Names.** A monument the register leaves unnamed gets a name from its description when that names it plainly
  ("O.L.Vrouwetoren.", VILLA "Rusthof").

## Licence

Code: MIT (see [LICENSE](LICENSE)). Data keeps the licence of its source: 3D BAG and 3D Basisvoorziening CC BY 4.0;
BAG, BGT, NWB, RCE and Wikidata CC0; Wikipedia text CC BY-SA; Wikimedia Commons photos each under their own licence,
credited in the app.
