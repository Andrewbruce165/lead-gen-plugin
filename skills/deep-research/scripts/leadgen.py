#!/usr/bin/env python3
"""leadgen.py — deterministic merge / score / tables for the deep-research skill (stdlib only).

  leadgen.py score  <icp_dir> [--n N]                   research/<channel>.json -> research/scored.json
  leadgen.py tables <icp_dir> [--n N] [--date YYYY-MM-DD] scored+verified+contacts -> companies-*.{md,csv}, people-*.{md,csv}
"""
import argparse, csv, json, math, re
from datetime import date, timedelta
from pathlib import Path

RESERVED = {"scored.json", "verified.json", "contacts.json"}
LEGAL = re.compile(r"\b(llc|ltd|inc|gmbh|ag|sa|srl|bv|oy|ab|plc|co|company|fze|fzco|dmcc|ооо|оао|зао|ао|ип)\b\.?")
CHANNEL_FIELDS = ("website", "linkedin", "instagram", "facebook", "google_maps", "reviews", "country", "why")


def norm_domain(url):
    if not url:
        return ""
    d = re.sub(r"^https?://", "", str(url).strip().lower())
    d = re.sub(r"^www\.", "", d)
    return d.split("/")[0].split("?")[0]


def norm_name(name):
    n = re.sub(r"[^\w\s]", " ", (name or "").lower())
    n = LEGAL.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def key(c):
    return norm_domain(c.get("domain") or c.get("website")) or ("name:" + norm_name(c.get("company")))


def merge(records):
    out = {}
    for c in records:
        k = key(c)
        if k in ("", "name:"):
            continue
        m = out.setdefault(k, {"company": c.get("company"), "domain": norm_domain(c.get("domain") or c.get("website")),
                                "evidence": [], "public_contacts": [], "channels": []})
        for f in CHANNEL_FIELDS:
            if c.get(f) and not m.get(f):
                m[f] = c[f]
        seen = {(e.get("criterion"), e.get("url")) for e in m["evidence"]}
        for e in c.get("evidence") or []:
            if (e.get("criterion"), e.get("url")) not in seen:
                m["evidence"].append(e)
                seen.add((e.get("criterion"), e.get("url")))
        seen_c = {(p.get("type"), p.get("value")) for p in m["public_contacts"]}
        for p in c.get("public_contacts") or []:
            if (p.get("type"), p.get("value")) not in seen_c:
                m["public_contacts"].append(p)
                seen_c.add((p.get("type"), p.get("value")))
        ch = c.get("_channel")
        if ch and ch not in m["channels"]:
            m["channels"].append(ch)
    return list(out.values())


def excluded(c, icp):
    for x in icp.get("exclusions") or []:
        if x.get("domain") and norm_domain(x["domain"]) == c["domain"]:
            return True
        if x.get("name") and norm_name(x["name"]) == norm_name(c["company"]):
            return True
    return False


def recent(e, today):
    """Trigger counts if undated or dated within the last 12 months."""
    d = e.get("date")
    if not d:
        return True
    try:
        y, m = (str(d).split("-") + ["01"])[:2]
        return date(int(y), int(m), 1) >= today - timedelta(days=365)
    except ValueError:
        return True


def score(c, icp, today):
    """60 must-have (all required, else None) + 25 nice-to-have + 15 triggers (recent only)."""
    found = {e["criterion"] for e in c["evidence"] if e.get("found") and e.get("url")}
    must = [x["id"] for x in icp["must_have"]]
    if any(i not in found for i in must):
        return None
    nice = [x["id"] for x in icp.get("nice_to_have") or []]
    trig = [x["id"] for x in icp.get("triggers") or []]
    trig_found = {e["criterion"] for e in c["evidence"]
                  if e.get("found") and e.get("url") and e["criterion"] in trig and recent(e, today)}
    s = 60.0
    if nice:
        s += 25.0 * sum(i in found for i in nice) / len(nice)
    if trig:
        s += 15.0 * sum(i in trig_found for i in trig) / len(trig)
    return int(round(s))


def cmd_score(d, n):
    icp = json.loads((d / "icp.json").read_text())
    today = date.today()
    records = []
    for f in sorted((d / "research").glob("*.json")):
        if f.name in RESERVED:
            continue
        data = json.loads(f.read_text() or "[]")
        for c in data:
            c["_channel"] = f.stem
        records += data
    merged = merge(records)
    scored = []
    for c in merged:
        if excluded(c, icp):
            continue
        s = score(c, icp, today)
        if s is None:
            continue
        c["score"] = s
        scored.append(c)
    scored.sort(key=lambda c: (-c["score"], c["company"] or ""))
    keep = scored[: math.ceil(n * 1.3)]
    (d / "research" / "scored.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1))
    print(f"raw={len(records)} merged={len(merged)} scored={len(scored)} kept={len(keep)}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("score", "tables"):
        s = sub.add_parser(name)
        s.add_argument("icp_dir", type=Path)
        s.add_argument("--n", type=int, default=40)
        if name == "tables":
            s.add_argument("--date", default=date.today().isoformat())
    a = p.parse_args()
    if a.cmd == "score":
        cmd_score(a.icp_dir, a.n)
    else:
        cmd_tables(a.icp_dir, a.n, a.date)  # Task 5


if __name__ == "__main__":
    main()
