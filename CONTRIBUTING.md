# Adding a city or a layer

## A city

Add `cities/<name>.json`, modelled on an existing one (see the README), and run:

```bash
python -m pipeline.run <name>
python -m http.server 8642 --directory web    # http://localhost:8642/?city=<name>
```

The periods are the city's own growth phases, not decades: ten at most, each with a colour from the shared palette.

## A layer

A context layer lights up a set of buildings that share a piece of history. Add a function to
[`pipeline/layers.py`](pipeline/layers.py) with the `@layer(...)` decorator, with every text in English and Dutch
(`title` / `title_nl`, ...) and group labels as `(key, English, Dutch)`. It returns `{BAG pand id: group}`. Helpers
are there for the common joins: `by_monument({monument number: group})` and `within(polygons, column)`.

Only openly licensed data can go in; add its download to a `s00_fetch_*` step and say which licence it carries. Check
the layer with:

```bash
python -m pipeline.run <name> s05 s03    # counts per group, then the tiles
```
