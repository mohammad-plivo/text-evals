"""Spend control for the leader text lane: one shared ledger with a hard cap, and an in-process wire meter.

Ledger (text-lane/ledger.json, fcntl lock on ledger.json.lock, shared with the v29_model_eval port):
  {cap_usd: 200, spent_usd, reserved_usd, entries: [{id, campaign, label, status, reserved_usd, actual_usd, ...}]}
A run reserves before it starts and settles after; a reservation that would pass the cap (or the campaign's
sub-cap) is refused. Settled cost = provider-returned usage x PRICES; a request with no returned usage settles
at its conservative bound.

Wire meter (install() in the run process): every httpx/aiohttp request is classified by host. Priced hosts
(Jev, LiveKit gateway, Azure) get a conservative bound BEFORE sending and are refused once the run's budget
would pass; the bound is replaced by the real cost when the usage comes back. E2B and GETs (pool warm-ups,
listings: no prompt, nothing billed) are counted; any other host is refused, so nothing leaves the process unseen.

PRICES, USD per 1M tokens (input, output). Sources and assumptions:
  jev    0.042 in  - docs.typesafe.ai/models, as recorded by scripts/jev_paid_smoke.py (not re-checked today);
         0.168 out - UNVERIFIED, assumed 4x input (Jev returns a few hundred tokens of answers).
  gemma  0.40 / 1.20 - livekit.com/pricing/inference for google/gemma-4-31b-it, as recorded by paid_exact_flow.py.
  azure  2.00 / 8.00 - Azure OpenAI gpt-4.1 global standard list price; cached input is billed at the full rate.
  e2b    flat E2B_RUN_USD per run - assumption: one 2-vCPU sandbox (~$0.0001/s) alive a few minutes.
Conservative bound per request: input tokens <= body bytes + 512 (a token is at least one byte), output tokens
<= the request's max_tokens or OUT_BOUND, both priced at CONSERVATIVE_FACTOR x PRICES.
"""
from __future__ import annotations

import contextlib
import fcntl
import itertools
import json
import os
import tempfile
import threading
import time
import uuid

LANE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(LANE, "ledger.json")
CAP_USD = 200.0
PRICES = {"jev": (0.042, 0.168), "gemma": (0.40, 1.20), "azure": (2.00, 8.00)}
OUT_BOUND = {"jev": 2048, "gemma": 1024, "azure": 512}
CONSERVATIVE_FACTOR = 2.0
E2B_RUN_USD = 0.01
EXACT = {"api.typesafe.ai": "jev", "agent-gateway.livekit.cloud": "gemma", "api.e2b.app": "e2b"}
SUFFIX = ((".openai.azure.com", "azure"), (".services.ai.azure.com", "azure"), (".cognitiveservices.azure.com", "azure"),
          (".e2b.app", "e2b"), (".e2b.dev", "e2b"))
LOCAL = {"127.0.0.1", "localhost", "::1"}


class Refused(RuntimeError):
    pass


def dest_of(host: str) -> str | None:
    host = (host or "").lower()
    if host in EXACT:
        return EXACT[host]
    for suffix, dest in SUFFIX:
        if host.endswith(suffix):
            return dest
    return "local" if host in LOCAL else None


def cost(dest: str, tokens_in: float, tokens_out: float, factor: float = 1.0) -> float:
    pin, pout = PRICES.get(dest, (0.0, 0.0))
    return factor * (tokens_in * pin + tokens_out * pout) / 1e6


# ---------------------------------------------------------------- ledger

@contextlib.contextmanager
def _locked():
    with open(LEDGER + ".lock", "a+b") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _read() -> dict:
    if not os.path.exists(LEDGER):
        return {"cap_usd": CAP_USD, "spent_usd": 0.0, "reserved_usd": 0.0, "entries": []}
    led = json.load(open(LEDGER))
    if not all(k in led for k in ("cap_usd", "spent_usd", "reserved_usd", "entries")):
        raise Refused("ledger.json has an unexpected shape; refusing to touch it")
    return led


def _write(led: dict) -> None:
    # recomputed from the entries every write, so the totals can never drift from the records
    led["spent_usd"] = round(sum(e.get("actual_usd") or 0 for e in led["entries"] if e.get("status") == "settled"), 6)
    led["reserved_usd"] = round(sum(e.get("reserved_usd") or 0 for e in led["entries"] if e.get("status") == "reserved"), 6)
    fd, tmp = tempfile.mkstemp(dir=LANE, prefix=".ledger.", suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump(led, fh, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, LEDGER)


def _exposure(e: dict) -> float:
    return (e.get("actual_usd") or 0) if e.get("status") == "settled" else (e.get("reserved_usd") or 0)


def reserve(campaign: str, label: str, usd: float, campaign_cap: float | None = None) -> str:
    with _locked():
        led = _read()
        total = led["spent_usd"] + led["reserved_usd"]
        if total + usd > float(led["cap_usd"]) + 1e-9:
            raise Refused(f"cap: {total:.4f} committed + {usd:.2f} would pass ${led['cap_usd']}")
        mine = sum(_exposure(e) for e in led["entries"] if e.get("campaign") == campaign)
        if campaign_cap is not None and mine + usd > campaign_cap + 1e-9:
            raise Refused(f"campaign {campaign}: {mine:.4f} committed + {usd:.2f} would pass ${campaign_cap}")
        entry = {"id": uuid.uuid4().hex[:12], "campaign": campaign, "label": label, "status": "reserved",
                 "reserved_usd": round(usd, 6), "actual_usd": None, "source": "text-lane/meter.py",
                 "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        led["entries"].append(entry)
        _write(led)
        return entry["id"]


def settle(entry_id: str, actual_usd: float, detail: dict | None = None) -> None:
    with _locked():
        led = _read()
        entry = next(e for e in led["entries"] if e["id"] == entry_id)
        entry.update(status="settled", actual_usd=round(actual_usd, 6), settled=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                     detail=detail or {})
        _write(led)


def settle_from_meter(path: str) -> tuple[float, dict]:
    """Actual cost of one run from its wire log: returned usage where it came back, the bound where it did not."""
    sent, done, counted = {}, {}, []
    for line in open(path) if os.path.exists(path) else ():
        ev = json.loads(line)
        if ev["ev"] == "count":
            counted.append(ev)
        (sent if ev["ev"] == "sent" else done if ev["ev"] == "done" else {})[ev.get("id")] = ev
    by = {}
    for ev in counted:
        row = by.setdefault(ev["dest"], {"requests": 0, "usd": 0.0, "unsettled": 0, "tokens_in": 0, "tokens_out": 0})
        row["requests"] += 1
    for rid, s in sent.items():
        d = done.get(rid)
        usd = d["actual_usd"] if d and d.get("actual_usd") is not None else s["bound_usd"]
        row = by.setdefault(s["dest"], {"requests": 0, "usd": 0.0, "unsettled": 0, "tokens_in": 0, "tokens_out": 0})
        row["requests"] += 1
        row["usd"] += usd
        row["unsettled"] += 0 if d and d.get("actual_usd") is not None else 1
        row["tokens_in"] += (d or {}).get("tokens_in") or 0
        row["tokens_out"] += (d or {}).get("tokens_out") or 0
    total = sum(r["usd"] for r in by.values()) + (E2B_RUN_USD if "e2b" in by else 0.0)
    return round(total, 6), {k: {**v, "usd": round(v["usd"], 6)} for k, v in by.items()}


# ---------------------------------------------------------------- wire meter

class _Meter:
    def __init__(self, path: str, budget_usd: float):
        self.path, self.budget, self.committed = path, budget_usd, 0.0
        self.bounds: dict[int, tuple[str, float]] = {}  # request id -> the wire log it was committed under, its bound
        self.lock = threading.Lock()
        self.ids = itertools.count(1)
        self.refusals: list[str] = []

    def log(self, **ev) -> None:
        with self.lock, open(self.path, "a") as fh:
            fh.write(json.dumps(ev, default=str) + "\n")

    def before(self, dest: str, host: str, path: str, body: bytes, method: str = "POST") -> int | None:
        rid = next(self.ids)
        if dest in (None, "local") and host not in LOCAL:
            self.refusals.append(f"denied host {host}")
            self.log(ev="denied", id=rid, host=host, path=path)
            raise Refused(f"text lane: host {host} is not on the allow-list")
        if dest not in PRICES or method == "GET":  # a GET carries no prompt: a pool warm-up or a listing, never billed
            self.log(ev="count", id=rid, dest=dest, host=host, path=path, t=time.time())
            return None
        req = {}
        with contextlib.suppress(Exception):
            req = json.loads(body or b"{}")
        out = req.get("max_completion_tokens") or req.get("max_tokens") or OUT_BOUND[dest]
        bound = cost(dest, len(body or b"") + 512, out, CONSERVATIVE_FACTOR)
        with self.lock:
            if self.committed + bound > self.budget:
                self.refusals.append(f"budget {dest}")
                refused = True
            else:
                self.committed += bound
                self.bounds[rid] = (self.path, bound)
                refused = False
        if refused:
            self.log(ev="refused", id=rid, dest=dest, bound_usd=bound, committed=self.committed, budget=self.budget)
            raise Refused(f"text lane: run budget ${self.budget:.2f} would pass")
        self.log(ev="sent", id=rid, dest=dest, host=host, path=path, model=req.get("model"), bytes=len(body or b""),
                 bound_usd=round(bound, 6), t=time.time())
        return rid

    def after(self, rid: int | None, dest: str, status: int, body: bytes, bound_hint: float = 0.0) -> None:
        if rid is None:
            return
        usage, model = _usage(body)
        tin = usage.get("prompt_tokens") or usage.get("input_tokens")
        tout = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        estimated = tin is None
        actual = None if estimated else cost(dest, tin, tout)
        with self.lock:
            committed_under, bound = self.bounds.pop(rid, (None, 0.0))
            # a new wire log is a new budget: a request committed under the old one never settles into it
            if actual is not None and committed_under == self.path:
                self.committed += actual - bound
        if estimated:  # no usage returned: the bound stays committed and is what the ledger settles
            self.log(ev="done", id=rid, dest=dest, status=status, model=model, usage_keys=sorted(usage),
                     estimated=True, actual_usd=None, t=time.time())
            return
        self.log(ev="done", id=rid, dest=dest, status=status, model=model, usage_keys=sorted(usage), tokens_in=tin,
                 tokens_out=tout, actual_usd=round(actual, 8), t=time.time())


def _usage(body: bytes) -> tuple[dict, str | None]:
    """Usage and served model from a JSON body or an SSE stream (last chunk carrying usage wins)."""
    text = (body or b"").decode("utf-8", "replace").strip()
    objs = []
    if text.startswith("{"):
        with contextlib.suppress(ValueError):
            objs = [json.loads(text)]
    else:
        for line in text.splitlines():
            if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
                with contextlib.suppress(ValueError):
                    objs.append(json.loads(line[5:]))
    usage, model = {}, None
    for o in objs:
        if isinstance(o, dict):
            model = o.get("model") or model
            if isinstance(o.get("usage"), dict):
                usage = o["usage"]
    return usage, model


METER: _Meter | None = None


def install(path: str, budget_usd: float) -> _Meter:
    """Patch httpx (async and sync) and aiohttp in this process. Call before anything opens a client."""
    global METER
    import httpx

    METER = m = _Meter(path, budget_usd)

    class _Tee(httpx.AsyncByteStream):
        def __init__(self, inner, finish):
            self.inner, self.finish, self.buf, self.closed = inner, finish, [], False

        async def __aiter__(self):
            async for chunk in self.inner:
                self.buf.append(chunk)
                yield chunk

        async def aclose(self):
            with contextlib.suppress(Exception):
                await self.inner.aclose()
            if not self.closed:
                self.closed = True
                self.finish(b"".join(self.buf))

    def body_of(request) -> bytes:
        try:
            return request.content
        except Exception:  # a streamed upload: counted, size unknown
            return b""

    orig_async = httpx.AsyncClient.send

    async def send(self, request, *args, **kwargs):
        dest = dest_of(request.url.host)
        body = body_of(request)
        try:
            rid = m.before(dest, request.url.host, request.url.path, body if dest in PRICES else b"", request.method)
        except Refused as exc:
            raise httpx.ConnectError(str(exc), request=request) from exc
        resp = await orig_async(self, request, *args, **kwargs)
        if rid is not None:
            if kwargs.get("stream"):
                resp.stream = _Tee(resp.stream, lambda b: m.after(rid, dest, resp.status_code, b))
            else:
                m.after(rid, dest, resp.status_code, resp.content)
        return resp

    httpx.AsyncClient.send = send

    orig_sync = httpx.Client.send

    def send_sync(self, request, *args, **kwargs):
        dest = dest_of(request.url.host)
        body = body_of(request)
        try:
            rid = m.before(dest, request.url.host, request.url.path, body if dest in PRICES else b"", request.method)
        except Refused as exc:
            raise httpx.ConnectError(str(exc), request=request) from exc
        resp = orig_sync(self, request, *args, **kwargs)
        if rid is not None and not kwargs.get("stream"):
            m.after(rid, dest, resp.status_code, resp.content)
        elif rid is not None:
            m.log(ev="done", id=rid, dest=dest, status=resp.status_code, estimated=True, actual_usd=None)
        return resp

    httpx.Client.send = send_sync

    with contextlib.suppress(ImportError):
        import aiohttp
        orig_req = aiohttp.ClientSession._request

        async def _request(self, method, str_or_url, *args, **kwargs):
            host = aiohttp.client.URL(str(str_or_url)).host or ""
            dest = dest_of(host)
            if dest in PRICES:  # a priced call we cannot meter here: refuse rather than bill blind
                m.refusals.append(f"unmetered aiohttp {host}")
                raise aiohttp.ClientConnectionError(f"text lane: {host} over aiohttp is not metered")
            try:
                m.before(dest, host, "aiohttp", b"")
            except Refused as exc:
                raise aiohttp.ClientConnectionError(str(exc)) from exc
            return await orig_req(self, method, str_or_url, *args, **kwargs)

        aiohttp.ClientSession._request = _request
    return m
