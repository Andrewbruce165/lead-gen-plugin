#!/usr/bin/env python3
"""Self-check for leadgen.py. Run: python3 test_leadgen.py"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
SCRIPT = HERE / "leadgen.py"

ICP = {
    "slug": "t", "label": "test", "n": 2,
    "must_have": [{"id": "M1", "text": "a"}, {"id": "M2", "text": "b"}],
    "nice_to_have": [{"id": "N1", "text": "c"}, {"id": "N2", "text": "d"}],
    "triggers": [{"id": "T1", "text": "hiring", "where": "jobs"}],
    "exclusions": [{"name": "Old Client LLC", "domain": "oldclient.com"}],
    "decision_makers": [], "search_plan": [],
}

def ev(*ids, date=None):
    return [{"criterion": i, "found": True, "url": f"https://src/{i}", "date": date} for i in ids]

def company(name, domain, evidence, **kw):
    c = {"company": name, "domain": domain, "website": f"https://{domain}", "evidence": evidence, "public_contacts": []}
    c.update(kw); return c

def run(*args):
    r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout

def setup():
    d = Path(tempfile.mkdtemp()); (d / "research").mkdir()
    (d / "icp.json").write_text(json.dumps(ICP))
    return d

def test_score():
    d = setup()
    # channel A: full match with recent trigger + a dup of Beta with www prefix
    (d / "research" / "registries.json").write_text(json.dumps([
        company("Alpha", "alpha.com", ev("M1", "M2", "N1", "N2") + ev("T1", date="2026-08"),
                public_contacts=[{"type": "phone", "value": "+1", "source": "website", "source_url": "https://alpha.com"}]),
        company("Beta Ltd", "www.beta.com", ev("M1", "M2")),
        company("Old Client LLC", "oldclient.com", ev("M1", "M2", "N1", "N2")),      # excluded
        company("NoMust", "nomust.com", ev("M1", "N1", "N2")),                       # missing M2 -> dropped
    ]))
    # channel B: Beta again with extra nice-to-have + stale trigger
    (d / "research" / "social.json").write_text(json.dumps([
        company("Beta", "https://beta.com/", ev("N1") + ev("T1", date="2020-01"),
                public_contacts=[{"type": "email", "value": "hi@beta.com", "source": "linkedin", "source_url": "https://li"}]),
        company("Gamma", "gamma.com", ev("M1", "M2", "N1")),
    ]))
    run("score", str(d), "--n", "2")
    scored = json.loads((d / "research" / "scored.json").read_text())
    by = {c["domain"]: c for c in scored}
    assert "oldclient.com" not in by and "nomust.com" not in by, by.keys()
    assert by["alpha.com"]["score"] == 100
    assert by["beta.com"]["score"] == 60 + 12, by["beta.com"]["score"]        # merged: N1 found (12.5→ round 72), stale T1 ignored
    assert by["beta.com"]["channels"] == ["registries", "social"]
    assert len(by["beta.com"]["public_contacts"]) == 1
    assert [c["domain"] for c in scored] == ["alpha.com", "beta.com", "gamma.com"]  # ceil(2*1.3)=3 kept
    shutil.rmtree(d)
    print("test_score ok")

if __name__ == "__main__":
    test_score()
