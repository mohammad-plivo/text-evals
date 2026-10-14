"""Compare a run_live.py board with a Hunter run, scenario by scenario, and bucket the sim failures by criterion.
  board_compare.py --board DIR/board.json --payloads DIR --hunter-run board3-run.json [--md OUT.md]
"""
import argparse
import glob
import json
import os
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_live_twins import slug_of  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True); ap.add_argument("--payloads", required=True)
    ap.add_argument("--hunter-run", required=True); ap.add_argument("--md")
    a = ap.parse_args()
    board = json.load(open(a.board)); run = json.load(open(a.hunter_run))
    by_id = {str(x["scenario_id"]): x for x in run["items"]}
    slug2id, names = {}, {}
    for f in glob.glob(os.path.join(a.payloads, "*.json")):
        if not os.path.basename(f)[0].isdigit():
            continue
        s = json.load(open(f)); slug2id[slug_of(s["payload"]["event"])] = str(s["id"]); names[str(s["id"])] = s["name"]
    rows, buckets = [], {}
    for slug, res in sorted(board.items()):
        sid = slug2id.get(slug, ""); h = by_id.get(sid, {})
        runs = res.get("runs") or []
        sim = "PASS" if runs and all(r["pass"] for r in runs) else ("FAIL" if runs else "NO RUN")
        bad = sorted({str(c.get("n")) for r in runs for c in r["criteria"] if not c.get("met")})
        reasons = [(c.get("reason") or "")[:140] for r in runs for c in r["criteria"] if not c.get("met")]
        for n in bad:
            buckets.setdefault(n, []).append(slug)
        rows.append((slug, sid, names.get(sid, "")[17:60], h.get("result", "-"), h.get("score"), sim,
                     ",".join(bad), res.get("gemma_calls", 0), res.get("azure_calls", 0), reasons))
    agree = sum(1 for r in rows if (r[3] == "pass") == (r[5] == "PASS"))
    lines = [f"| twin | Hunter b3 | sim | not met | gemma/azure | scenario |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r[0]} | {r[3]} {r[4] if r[4] is not None else ''} | {r[5]} | {r[6]} | {r[7]}/{r[8]} | {r[2]} |")
    summary = (f"sim: {sum(1 for r in rows if r[5]=='PASS')}/{len(rows)} pass; Hunter board 3: {sum(1 for r in rows if r[3]=='pass')}/{len(rows)} pass; "
               f"agreement {agree}/{len(rows)}; sim-only fails: {[r[0] for r in rows if r[5]!='PASS' and r[3]=='pass']}; "
               f"Hunter-only fails: {[r[0] for r in rows if r[5]=='PASS' and r[3]!='pass']}")
    print(summary); print("\n".join(lines))
    print("\nsim failures by slug (reasons):")
    for r in rows:
        if r[5] == "FAIL":
            print(f"- {r[0]} notmet={r[6]}")
            for why in r[9][:3]:
                print(f"    {why}")
    if a.md:
        open(a.md, "w").write(summary + "\n\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
