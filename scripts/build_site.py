"""Put one city's viewer in a folder of its own, ready for static hosting (Cloudflare Pages): dist/<city>/.

  python scripts/build_site.py amersfoort

The folder holds the viewer (web/ without other cities' data), the city's data under data/<city>/, and pages that
open on the city and name it from the start. Build and deploy in one go with scripts/deploy.ps1.
"""
import json
import re
import shutil
import sys
from pathlib import Path

VIEWER = ["app.js", "styles.css", "logo.js", "worker.js", "vendor", "graph.js", "graph.css"]


def main():
    city = sys.argv[1]
    cfg = json.loads(Path(f"web/data/{city}/city.json").read_text(encoding="utf-8"))
    label, n = cfg["label"], cfg["stats"]["buildings"]
    out = Path("dist") / city
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in VIEWER:
        src = Path("web") / name
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, out / name)
    shutil.copytree(f"web/data/{city}", out / "data" / city)

    # The page names its city from the start, so nothing else shows before the map loads; noindex, it is a test.
    html = Path("web/index.html").read_text(encoding="utf-8")
    desc = f"All {n:,} buildings of {label} in 3D, coloured by the year they were built, with layers from the national monument register."
    html = html.replace('<html lang="en">', f'<html lang="en" data-city="{city}">', 1)
    noindex = '\n<meta name="robots" content="noindex">'
    html = re.sub(r"<title>.*?</title>", f"<title>LAYRS: {label}</title>{noindex}", html, count=1)
    html = re.sub(r'(<meta (?:name="description"|property="og:description") content=")[^"]*"',
                  lambda m: f'{m.group(1)}{desc}"', html)
    html = html.replace('<meta property="og:title" content="LAYRS">', f'<meta property="og:title" content="LAYRS: {label}">')
    html = html.replace('<span class="layrs" aria-label="LAYRS">LAYRS</span> <i', f'<span class="layrs" aria-label="LAYRS">LAYRS</span>{label}<i')
    (out / "index.html").write_text(html, encoding="utf-8")
    g = Path("web/graph.html").read_text(encoding="utf-8")
    g = g.replace('<html lang="en">', f'<html lang="en" data-city="{city}">', 1)
    g = re.sub(r"<title>.*?</title>", f"<title>LAYRS: {label} — the graph</title>{noindex}", g, count=1)
    g = g.replace('<span class="g-mark">LAYRS</span> </a>', f'<span class="g-mark">LAYRS</span>{label}</a>')
    (out / "graph.html").write_text(g, encoding="utf-8")
    # long cache for the heavy binary files, which change only with a new build
    (out / "_headers").write_text(f"/data/{city}/*.bin\n  Cache-Control: public, max-age=86400\n", encoding="utf-8")

    files = [f for f in out.rglob("*") if f.is_file()]
    big = max(files, key=lambda f: f.stat().st_size)
    print(f"{out}: {len(files)} files, {sum(f.stat().st_size for f in files) / 1e6:.1f} MB; largest {big.name} "
          f"{big.stat().st_size / 1e6:.1f} MB (Pages allows 20,000 files of at most 25 MiB)")


if __name__ == "__main__":
    main()
