"""The city's periods (cities/<city>.json). Boundaries follow the city's growth phases, not decades."""
from .city import CFG

# (key, label, start, end, colour) — oxblood brick for the oldest, through ochre and green, to slate and violet
PERIODS = [(k, label, a, b, col) for k, label, _, a, b, col in CFG["periods"]]
LABELS_NL = {label: nl for _, label, nl, _, _, _ in CFG["periods"]}

def period_index(year: int) -> int:
    for i, (_, _, a, b, _) in enumerate(PERIODS):
        if a <= year <= b:
            return i
    return 0
