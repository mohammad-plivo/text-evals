"""Board on one tree: later campaigns override earlier ones per case. Usage: board.py <campaign> ... (oldest first)."""
import json
import sys
from pathlib import Path

SE = Path(__file__).resolve().parent


def lane_a(c):
    f = SE / f"campaign-{c}/lane-a/results.jsonl"
    rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []
    return {r["case_id"]: (r["structural_status"] == "passed", "") for r in rows}


def lane_b(c):
    f = SE / f"campaign-{c}/lane-b/results.json"
    out = {}
    for log in json.loads(f.read_text())["logs"] if f.exists() else []:
        if log.get("report") and Path(log["report"]).exists():
            for run in json.loads(Path(log["report"]).read_text()):
                out[run["scenario"]] = (not run["failures"], "; ".join(run["failures"])[:160])
    return out


def board(campaigns, lane, bar_file):
    res = {}
    for c in campaigns:
        res.update(lane(c))
    bar = (SE / bar_file).read_text().split()
    rows = [(s, *res.get(s, (None, "no result"))) for s in bar]
    return sum(1 for _, ok, _ in rows if ok), len(bar), [r for r in rows if not r[1]]


if __name__ == "__main__":
    cs = sys.argv[1:]
    for name, lane, bar in (("lane A", lane_a, "pass-bar-lane-a.txt"), ("lane B", lane_b, "pass-bar-lane-b.txt")):
        p, n, bad = board(cs, lane, bar)
        print(f"{name}: {p}/{n} in-bar passed")
        for s, ok, why in bad:
            print(f"  {'NO RESULT' if ok is None else 'FAIL'} {s} | {why}")
