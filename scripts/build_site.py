"""Put one city's viewer in a folder of its own, ready for static hosting (Cloudflare Pages): dist/<city>/.

  uv run python scripts/build_site.py amersfoort

The folder holds the viewer (web/ without other cities' data), the city's data under data/<city>/, and an index.html
that opens on the city. Its head describes the city instead of Amsterdam's live site: no canonical link or
structured data pointing there, no Amsterdam preview image, and noindex, since this is a test. Deploy with
  npx wrangler pages deploy dist/<city> --project-name layrs-<city>
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

    html = Path("web/index.html").read_text(encoding="utf-8")
    desc = f"All {n:,} buildings of {label} in 3D, coloured by the year they were built, with layers from the national monument register."
    html = html.replace('<html lang="en">', f'<html lang="en" data-city="{city}">', 1)
    html = re.sub(r"<title>.*?</title>", f"<title>LAYRS: {label}</title>", html, count=1)
    html = re.sub(r'<meta name="description" content="[^"]*">',
                  f'<meta name="description" content="{desc}">\n<meta name="robots" content="noindex">', html, count=1)
    html = re.sub(r'<link rel="canonical"[^>]*>\n', "", html)
    html = re.sub(r'<meta property="og:(url|image)[^>]*>\n', "", html)
    html = re.sub(r'<meta property="og:title" content="[^"]*">', f'<meta property="og:title" content="LAYRS: {label}">', html)
    html = re.sub(r'<meta property="og:description" content="[^"]*">', f'<meta property="og:description" content="{desc}">', html)
    html = re.sub(r'<link rel="alternate" type="text/csv"[^>]*>\n', "", html)
    html = re.sub(r'<script type="application/ld\+json">.*?</script>\n', "", html, flags=re.S)
    html = re.sub(r"<noscript>.*?</noscript>", "<noscript><p style=\"padding:24px;font:16px sans-serif\">This map needs JavaScript.</p></noscript>", html, flags=re.S)
    html = html.replace("aria-label=\"3D map of Amsterdam's buildings\"", f"aria-label=\"3D map of {label}'s buildings\"")
    (out / "index.html").write_text(html, encoding="utf-8")
    if cfg.get("features", {}).get("graph"):
        g = Path("web/graph.html").read_text(encoding="utf-8")
        g = g.replace('<html lang="en">', f'<html lang="en" data-city="{city}">', 1)
        g = re.sub(r"<title>.*?</title>", f'<title>LAYRS: {label} — the graph</title>\n<meta name="robots" content="noindex">',
                   g, count=1)
        g = g.replace('<span class="g-mark">LAYRS</span>Amsterdam', f'<span class="g-mark">LAYRS</span>{label}')
        (out / "graph.html").write_text(g, encoding="utf-8")
    # long cache for the heavy binary files, which change only with a new build
    (out / "_headers").write_text(f"/data/{city}/*.bin\n  Cache-Control: public, max-age=86400\n", encoding="utf-8")

    files = [f for f in out.rglob("*") if f.is_file()]
    big = max(files, key=lambda f: f.stat().st_size)
    print(f"{out}: {len(files)} files, {sum(f.stat().st_size for f in files) / 1e6:.1f} MB; largest {big.name} "
          f"{big.stat().st_size / 1e6:.1f} MB (Pages allows 20,000 files of at most 25 MiB)")


if __name__ == "__main__":
    main()
