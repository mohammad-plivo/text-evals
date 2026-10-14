"""Grade sim runs with the Hunter scenario's own evaluationPrompt, one verdict per criterion.

Usage: uv run --frozen python V29-Hunter-Example/hunter-sim/judge.py <worktree> <slug|all> [--deployment gpt-4.1]
Reads the newest reports/*.json in each workspace, writes reports/<stamp>.judged.json and prints a board.
"""
import asyncio, glob, json, os, re, sys

WT = sys.argv[1]; WHICH = sys.argv[2] if len(sys.argv) > 2 else "all"
DEPLOYMENT = sys.argv[sys.argv.index("--deployment") + 1] if "--deployment" in sys.argv else "gpt-4.1"
ROOT = os.path.join(WT, "eval_tests", "v29ex_hunter")
if "--env-file" in sys.argv:  # the judge speaks to Azure through the same env the sim uses
    for line in open(sys.argv[sys.argv.index("--env-file") + 1]):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"'))
sys.path.insert(0, WT)
from src.simulation.cli import azure_chat  # noqa: E402

FORMAT = (
    "\n\nOUTPUT FORMAT, strictly: one line per numbered criterion, in order, exactly\n"
    "<number>: [MET] or [NOT MET] accuracy=<0-100> - <one sentence of evidence quoting the transcript>\n"
    "then a final line: SCORE=<met>/<total>. No other text."
)


def transcript(ws: str, run: dict) -> str:
    """Observed speech only. The end node now runs in the sim (H-2), so nothing is synthesised here."""
    lines = []
    for t in run.get("turns", []):
        if t.get("user"): lines.append(f"CALLER: {t['user']}")
        if t.get("agent"): lines.append(f"AGENT: {t['agent']}")
    return "\n".join(lines)


async def grade(ws: str) -> dict | None:
    if not os.path.exists(os.path.join(ws, "hunter.json")):
        return None  # the root workspace's own reports/ and scenarios/ directories are not scenarios
    h = json.load(open(os.path.join(ws, "hunter.json")))
    reports = sorted(p for p in glob.glob(os.path.join(ws, "reports", "*.json")) if not p.endswith(".judged.json"))
    if not reports: return None
    runs = json.load(open(reports[-1])); out = []
    for run in runs:
        system = h["evaluationPrompt"] + FORMAT
        prompt = "TRANSCRIPT (CALLER is the simulated customer, AGENT is the system under test):\n\n" + transcript(ws, run) + \
                 f"\n\nCall ended by the agent: {any(t.get('ended') for t in run.get('turns', []))}. Harness failures: {run.get('failures') or 'none'}."
        text = await azure_chat.chat(system, prompt, deployment=DEPLOYMENT)
        verdicts = re.findall(r"^\s*(\d+)\s*:\s*\[(MET|NOT MET)\]", text, re.M)
        met = sum(1 for _, v in verdicts if v == "MET"); total = len(verdicts) or 1
        score = met / total; passed = score >= float(h.get("evaluationThreshold", 0.8))
        out.append({"scenario": run.get("scenario"), "run": run.get("run"), "score": round(score, 2), "passed": passed,
                    "met": met, "total": total, "ended": any(t.get("ended") for t in run.get("turns", [])), "turns": len(run.get("turns", [])),
                    "failures": run.get("failures"), "verdict_text": text})
    path = reports[-1].replace(".json", ".judged.json"); json.dump(out, open(path, "w"), indent=1)
    return {"slug": os.path.basename(ws), "name": h["name"], "runs": out}


async def main() -> None:
    dirs = sorted(d for d in glob.glob(os.path.join(ROOT, "*")) if os.path.isdir(d) and (WHICH == "all" or os.path.basename(d) == WHICH))
    results = [r for r in await asyncio.gather(*(grade(d) for d in dirs)) if r]
    passed = 0
    print("| # | scenario | runs | passed | worst NOT MET |"); print("|---|---|---|---|---|")
    for i, r in enumerate(results, 1):
        ok = sum(1 for x in r["runs"] if x["passed"]); n = len(r["runs"]); passed += ok == n and n > 0
        worst = next((l.strip() for x in r["runs"] if not x["passed"] for l in x["verdict_text"].splitlines() if "[NOT MET]" in l), "")
        print(f"| {i} | {r['name'][:60]} | {n} | {ok}/{n} | {worst[:110]} |")
    print(f"\nscenarios fully passing: {passed}/{len(results)}")


asyncio.run(main())
