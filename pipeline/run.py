"""Run a city's pipeline: the steps listed in cities/<city>.json, in order, each as its own process.

  uv run python -m pipeline.run amersfoort                 every step
  uv run python -m pipeline.run amersfoort s05 s03         only these steps (by prefix)
  uv run python -m pipeline.run amersfoort --from s02      from a step on
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main():
    city, args = sys.argv[1], sys.argv[2:]
    steps = json.loads(Path(f"cities/{city}.json").read_text(encoding="utf-8"))["steps"]
    if args[:1] == ["--from"]:
        steps = steps[next(i for i, s in enumerate(steps) if s.startswith(args[1])):]
    elif args:
        steps = [s for s in steps if any(s.startswith(a) for a in args)]
    # PYTHONUTF8: the steps open files without naming an encoding, which on Windows would not be UTF-8
    env = dict(os.environ, CITY=city, PYTHONUTF8="1")
    for s in steps:
        t = time.time()
        print(f"== {city}: {s}", flush=True)
        subprocess.run([sys.executable, "-m", f"pipeline.{s}"], env=env, check=True)
        print(f"   {time.time() - t:.0f} s", flush=True)


if __name__ == "__main__":
    main()
