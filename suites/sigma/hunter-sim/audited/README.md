# Audited Hunter-to-simulator candidate

This isolated candidate fixes conversion provenance and strict report parsing without changing the historical harness or results.

Convert into a brand-new directory:

```sh
python3 Sigma/hunter-sim/audited/convert.py Sigma/hunter/scenarios /tmp/sigma-audited-new --inbound-number +15550100000
```

Run the pure offline checks:

```sh
python3 -m pytest -q Sigma/hunter-sim/audited/test_audited.py
```

`judge.py` requires an explicit JSON report manifest; it never discovers "latest" reports. Its output is simulator evidence, not Hunter-equivalent scoring. It makes a paid model call only when explicitly invoked.

There is deliberately no runner. The conversion manifest records timestamps and artifact/converter hashes but declares `execution_ready: false`; it does not yet pin a source revision, tracked-dirty state, simulator model, judge model, or a spend/concurrency budget. Do not use this candidate to launch paid runs until those controls are designed and reviewed.
