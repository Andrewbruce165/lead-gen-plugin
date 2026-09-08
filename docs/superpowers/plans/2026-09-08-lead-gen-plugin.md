# Lead Gen Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Code plugin `lead-gen`: `/lead-gen` → интервью строит ICP → оркестратор параллельных агентов находит, проверяет и обогащает контактами компании → две таблицы (`companies-*`, `people-*`) в `.md` и `.csv`.

**Architecture:** Плагин почти целиком из markdown: одна команда-вход, два скилла (`icp-builder`, `deep-research`) и три шаблона промптов для subagent'ов. Единственный код — stdlib-скрипт `leadgen.py` (merge по домену, детерминированный скоринг 60/25/15, рендер таблиц), потому что арифметика и CSV на 50 строк у LLM «в голове» ненадёжны. Агенты пишут сырые JSON в `leads/<slug>/research/`, оркестратор вызывает скрипт.

**Tech Stack:** Claude Code plugin format (`.claude-plugin/plugin.json`, `commands/*.md`, `skills/*/SKILL.md`), Python 3 stdlib (json, csv, re, argparse, datetime), Firecrawl-скиллы + WebSearch/WebFetch у subagent'ов.

**Spec:** `docs/superpowers/specs/2026-09-08-lead-gen-plugin-design.md`

## Global Constraints

- Плагин называется `lead-gen`; скиллы вызываются как `lead-gen:icp-builder`, `lead-gen:deep-research`.
- Рабочая директория ICP — `leads/<slug>/` в cwd пользователя (не в директории плагина).
- Контакты везде в формате `значение_источник`, разделитель `; `, отсутствие — `—`.
- Скоринг: must-have 60 (компания без любого подтверждённого must-have исключается), nice-to-have 25 поровну, триггеры за 12 месяцев 15 поровну.
- Бюджет агента-канала на бесплатном тире: ≤ 15 search, ≤ 20 scrape; при платном ключе ×3.
- N по умолчанию 30–50 (в скрипте default `--n 40`); при N > 50 агенты делятся ещё и по региону/суб-сегменту.
- Только реальные действующие компании, каждый факт с source URL, только публичные данные.
- Язык диалога — как у пользователя; поисковые запросы — на языке целевого рынка.
- Никакого MCP-сервера, CRM, UI, БД.
- Python-код: без сторонних зависимостей.

---

### Task 1: Каркас плагина и проверочный скрипт

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `README.md`
- Create: `.gitignore`
- Create: `test.sh`

**Interfaces:**
- Produces: `test.sh` — единая точка проверки; последующие задачи добавляют в него строки.

- [ ] **Step 1: Написать `test.sh` (падает — файлов ещё нет)**

```bash
#!/usr/bin/env bash
# Единая проверка плагина: манифест, frontmatter скиллов и команд, python-тесты.
set -euo pipefail
cd "$(dirname "$0")"

python3 -c 'import json,sys; m=json.load(open(".claude-plugin/plugin.json")); assert m["name"]=="lead-gen", m' \
  && echo "ok plugin.json"

for f in commands/*.md; do
  grep -q '^description: ' "$f" || { echo "FAIL $f: no description"; exit 1; }
  echo "ok $f"
done

for f in skills/*/SKILL.md; do
  dir=$(basename "$(dirname "$f")")
  head -1 "$f" | grep -q '^---$' || { echo "FAIL $f: no frontmatter"; exit 1; }
  grep -q "^name: $dir\$" "$f" || { echo "FAIL $f: name != $dir"; exit 1; }
  grep -q '^description: ' "$f" || { echo "FAIL $f: no description"; exit 1; }
  echo "ok $f"
done

if [ -f skills/deep-research/scripts/test_leadgen.py ]; then
  python3 skills/deep-research/scripts/test_leadgen.py && echo "ok leadgen.py"
fi
echo ALL OK
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `chmod +x test.sh && ./test.sh`
Expected: FAIL — `No such file or directory: '.claude-plugin/plugin.json'`

- [ ] **Step 3: Создать манифест, README, .gitignore**

`.claude-plugin/plugin.json`:
```json
{
  "name": "lead-gen",
  "description": "B2B lead generation in two phases: ICP interview, then parallel deep research that finds, verifies and enriches companies and decision-makers.",
  "author": {
    "name": "AGS Venture Lab",
    "email": "invest@agsfoods.net"
  },
  "keywords": ["lead-generation", "icp", "b2b", "research", "firecrawl"]
}
```

`README.md`:
```markdown
# lead-gen — Claude Code plugin

Two-phase B2B lead generation.

1. `/lead-gen` — interview → Ideal Customer Profile saved to `leads/<slug>/icp-brief.md` + `icp.json`.
2. `deep-research` skill — parallel channel agents → deterministic scoring → verifier pass → contact enrichment → `companies-<date>.md/.csv` and `people-<date>.md/.csv`.

## Install (local)

```bash
claude --plugin-dir /path/to/lead-gen-plugin
```

Then type `/lead-gen`.

## Layout

```
.claude-plugin/plugin.json
commands/lead-gen.md
skills/icp-builder/SKILL.md
skills/deep-research/SKILL.md
skills/deep-research/prompts/{channel,verifier,contacts}.md
skills/deep-research/scripts/leadgen.py   # merge + score + tables (stdlib)
test.sh
```

## Check

```bash
./test.sh
```

Design: `docs/superpowers/specs/2026-09-08-lead-gen-plugin-design.md`.
```

`.gitignore`:
```
leads/
__pycache__/
.DS_Store
```

- [ ] **Step 4: Запустить проверку**

Run: `./test.sh`
Expected: `ok plugin.json`, затем `FAIL commands/*.md: no description` — glob без совпадений в bash остаётся литералом; это нормально до Task 2. Главное — первая строка прошла.

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin README.md .gitignore test.sh
git commit -m "feat: plugin scaffold and test.sh"
```

---

### Task 2: Команда-вход `/lead-gen`

**Files:**
- Create: `commands/lead-gen.md`

**Interfaces:**
- Consumes: скилл `lead-gen:icp-builder` (Task 3), `lead-gen:deep-research` (Task 7).

- [ ] **Step 1: Написать команду**

`commands/lead-gen.md`:
```markdown
---
description: Build an Ideal Customer Profile through a short interview, then run parallel deep research to find, verify and enrich matching companies and decision-makers.
---

You are starting the lead-gen pipeline.

1. Look for existing profiles: list directories under `leads/` in the current working directory (ignore if none).
   - If one or more `leads/<slug>/icp.json` exist, ask the user (one question, options): **(a)** start a new ICP interview, **(b)** run deep research on one of the existing ICPs (list slugs), **(c)** both — new ICP then research.
   - If none exist, go straight to the interview.
2. For a new ICP: tell the user in one line that you will ask 1–2 questions per turn (~8 turns max) and stop for confirmation before saving. Then invoke the `lead-gen:icp-builder` skill via the Skill tool and follow it exactly.
3. For research: invoke the `lead-gen:deep-research` skill via the Skill tool with the chosen slug and follow it exactly.

Do not run deep research without the user's explicit confirmation — the ICP skill asks for it at the end.
```

- [ ] **Step 2: Проверить frontmatter**

Run: `./test.sh`
Expected: `ok plugin.json`, `ok commands/lead-gen.md`, затем `FAIL skills/*/SKILL.md: no frontmatter` — скиллов ещё нет, это Task 3.

- [ ] **Step 3: Commit**

```bash
git add commands/lead-gen.md
git commit -m "feat: /lead-gen entry command"
```

---

### Task 3: Скилл `icp-builder`

**Files:**
- Create: `skills/icp-builder/SKILL.md`
- Create: `skills/icp-builder/icp-brief-template.md`
- Create: `skills/icp-builder/icp-example.json`
- Modify: `docs/superpowers/specs/2026-09-08-lead-gen-plugin-design.md` (раздел «Рабочая директория» — добавить `icp.json`)

**Interfaces:**
- Produces: `leads/<slug>/icp-brief.md` (для человека) и `leads/<slug>/icp.json` (для скрипта и агентов) со схемой:

```json
{
  "slug": "string",
  "label": "one-line ICP label",
  "n": 40,
  "offer": "string",
  "segment": "string",
  "firmographics": "string",
  "geography": {"countries": ["..."], "languages": ["..."]},
  "decision_makers": [{"title": "string", "role": "decision-maker|influencer|blocker"}],
  "core_pain": "string",
  "must_have":    [{"id": "M1", "text": "observable criterion"}],
  "nice_to_have": [{"id": "N1", "text": "observable criterion"}],
  "triggers":     [{"id": "T1", "text": "trigger", "where": "where evidence appears online"}],
  "disqualifiers": ["string"],
  "lookalike_anchor": "string",
  "exclusions": [{"name": "string", "domain": "string|null"}],
  "search_plan": [{"channel": "registries|maps_reviews|social|news_triggers|associations_events", "sources": ["..."], "queries": ["..."]}]
}
```

- [ ] **Step 1: Шаблон брифа**

`skills/icp-builder/icp-brief-template.md`:
```markdown
## ICP: {{label}}

**Offer:** {{offer}}
**Target segment:** {{segment}}
**Firmographics:** {{firmographics}}
**Geography & language:** {{countries}}; publishes in {{languages}}
**Decision-maker:** {{decision_makers — title (role), ...}}
**Core pain:** {{core_pain}}

**Buying triggers (observable):**
- T1 — {{text}} · evidence: {{where}}

**Must-have criteria:**
- M1 — {{text}}

**Nice-to-have criteria:**
- N1 — {{text}}

**Disqualifiers:**
- {{...}}

**Lookalike anchor:** {{lookalike_anchor}}

## Exclusion list
- {{name}} ({{domain or —}}) — existing customer | competitor

## Search plan
Language(s) for queries: {{languages}}

### registries
Sources: {{...}}
Queries:
- "..."

### maps_reviews
...

### social
...

### news_triggers
...

### associations_events
...
```

- [ ] **Step 2: Пример JSON**

`skills/icp-builder/icp-example.json`:
```json
{
  "slug": "uae-food-distributors",
  "label": "UAE HoReCa food distributors, 20–200 staff",
  "n": 40,
  "offer": "Frozen and chilled food supply contracts, AED 50k–500k/year, 1–3 month sales cycle",
  "segment": "Food distribution / HoReCa supply, B2B",
  "firmographics": "20–200 employees, 1–5 warehouses, privately owned, operating 3+ years",
  "geography": {"countries": ["United Arab Emirates"], "languages": ["English", "Arabic"]},
  "decision_makers": [
    {"title": "Procurement Manager", "role": "decision-maker"},
    {"title": "Owner / General Manager", "role": "decision-maker"},
    {"title": "Category Manager", "role": "influencer"},
    {"title": "Finance Manager", "role": "blocker"}
  ],
  "core_pain": "Unstable supply and price volatility of imported frozen goods",
  "must_have": [
    {"id": "M1", "text": "Distributes food to restaurants/hotels in the UAE (stated on website or directory)"},
    {"id": "M2", "text": "Has own cold-chain warehouse or fleet (photos, page, or job ads)"}
  ],
  "nice_to_have": [
    {"id": "N1", "text": "Lists 50+ SKUs or a product catalogue online"},
    {"id": "N2", "text": "Serves 2+ emirates"}
  ],
  "triggers": [
    {"id": "T1", "text": "Hiring procurement or supply-chain roles", "where": "LinkedIn Jobs, Bayt, Indeed"},
    {"id": "T2", "text": "Opened a new warehouse or branch", "where": "Company news, LinkedIn posts, Google Maps new location"}
  ],
  "disqualifiers": ["Pure retail without B2B", "Government-owned", "Under 10 employees"],
  "lookalike_anchor": "Acme Foods LLC — 80 staff, 2 warehouses, bought AED 300k/year because of price stability",
  "exclusions": [
    {"name": "Acme Foods LLC", "domain": "acmefoods.ae"},
    {"name": "BigRival Trading", "domain": "bigrival.com"}
  ],
  "search_plan": [
    {"channel": "registries", "sources": ["Dubai Chamber directory", "Yellow Pages UAE", "Kompass UAE"],
     "queries": ["food distributor Dubai HoReCa", "frozen food supplier UAE restaurants", "موزع مواد غذائية دبي"]},
    {"channel": "maps_reviews", "sources": ["Google Maps", "Yelp UAE"],
     "queries": ["food distribution company Dubai", "foodstuff trading Sharjah cold storage"]},
    {"channel": "social", "sources": ["LinkedIn company pages", "Instagram"],
     "queries": ["site:linkedin.com/company food distribution UAE", "foodstuff trading LLC Dubai instagram"]},
    {"channel": "news_triggers", "sources": ["Gulf News", "Zawya", "LinkedIn Jobs", "Bayt"],
     "queries": ["food distributor UAE new warehouse 2026", "procurement manager food distribution Dubai job"]},
    {"channel": "associations_events", "sources": ["Gulfood exhibitor list", "UAE Food & Beverage Business Group"],
     "queries": ["Gulfood 2026 exhibitors UAE distributor"]}
  ]
}
```

- [ ] **Step 3: SKILL.md**

`skills/icp-builder/SKILL.md`:
```markdown
---
name: icp-builder
description: Interview a sales manager to build a precise Ideal Customer Profile (ICP) and save it as leads/<slug>/icp-brief.md + icp.json for the deep-research skill. Use when the user wants to define who to sell to, build an ICP, or start lead generation.
---

# ICP Builder

## Role

You are a senior B2B growth strategist and lead-generation specialist. A sales manager comes to you with a product or offer. Interview them, build a precise ICP, and save it in two files the `deep-research` skill will consume.

You work in two phases: **Discovery** (interview) → **Delivery** (save files, offer research). Never deliver before Discovery is complete and confirmed.

## Phase 1 — Discovery

### Slots you must fill

Track these internally. Do not ask about a slot the user has already answered, even indirectly.

1. **Offer** — what is sold, the core value, price range / deal size, sales cycle
2. **Segment** — industry, sub-vertical, business model (B2B / B2C / marketplace / etc.)
3. **Firmographics** — company size (headcount, revenue, locations), maturity, ownership type
4. **Geography & language** — countries / regions / cities; the language(s) local companies publish in
5. **Decision-maker** — role / title of the buyer, who influences, who blocks
6. **Pain & trigger** — the problem that makes them buy; observable signals a company has it now (hiring, expansion, new location, funding, regulation, tech stack, reviews, tenders, seasonality)
7. **Proof** — existing customers or the best deal closed: who and why it worked
8. **Disqualifiers** — who looks like a fit but is not; who to exclude; known competitors
9. **Volume** — how many companies they want (default 40; range 30–50)

### Interview rules

- Ask **1–2 questions per turn**, never more. Start with the offer and best existing customer.
- Use the AskUserQuestion tool where possible; every question comes with **3–5 suggested options** so the user can pick or correct.
- After each answer, reflect what you now understand in one line, then ask the next question. Adapt to the previous answer.
- If an answer is vague ("mid-size companies"), push once for something observable (headcount range, revenue, number of locations, number of trucks, etc.).
- Ask geography explicitly and always ask which language(s) target companies publish in — this drives the search plan.
- Do not invent market facts, do not fill gaps with assumptions. If the user does not know, mark the slot `unknown` and move on.
- Stop interviewing once slots 1–6 and 8 are filled with observable criteria. Do not ask more than ~8 turns total.
- Every criterion must be observable from public sources. If it cannot be verified online ("bad internal processes"), convert it into a proxy that can ("3+ open ops vacancies", "reviews mentioning delays").

### Checkpoint

Before delivering, show a **Draft ICP** (10–15 lines, bullets) and ask: *"Anything wrong or missing? Say 'go' to save the brief."* Wait for confirmation. If corrected, update and show again. Also propose a short latin `slug` (e.g. `uae-food-distributors`) and let the user change it.

## Phase 2 — Delivery

On confirmation:

1. Create `leads/<slug>/` in the current working directory.
2. Write `leads/<slug>/icp-brief.md` following `icp-brief-template.md` in this skill's directory. Sections: ICP block, **Exclusion list**, **Search plan**.
   - Exclusion list = existing customers from slot 7 + competitors named in slot 8, with domain when known.
   - Search plan = 3–5 channels chosen for the geography/language: `registries` (business registries, chambers, Yellow Pages, Kompass), `maps_reviews` (Google Maps, local review platforms), `social` (LinkedIn, Instagram, Facebook, local networks), `news_triggers` (local news, job boards, tender portals, funding news), `associations_events` (industry associations, trade-show exhibitor lists). For each channel list concrete sources and 3–6 query patterns **in the target market's language(s)**.
3. Write `leads/<slug>/icp.json` following `icp-example.json` in this skill's directory exactly (same keys). Criterion ids: `M1..`, `N1..`, `T1..`. Every must-have / nice-to-have / trigger in the JSON must appear verbatim in the brief and vice versa.
4. Show the user the path of both files and a 3-line summary.
5. Ask (one question): *"Run deep research now for `<slug>`?"* Options: **Yes — run now**, **No — I'll run it later**. On yes, invoke the `lead-gen:deep-research` skill via the Skill tool with the slug.

## Constraints

- Conversation language follows the user; `icp-brief.md` and `icp.json` are in English, search queries in the target market's language(s).
- Never skip the checkpoint. Never write files during Discovery.
- No filler, no motivational commentary. Short questions, dense output.
```

- [ ] **Step 4: Обновить спеку — одна строка про `icp.json`**

В `docs/superpowers/specs/2026-09-08-lead-gen-plugin-design.md`, раздел «Рабочая директория», после строки `├── icp-brief.md              # Phase 1 output` добавить:
```
├── icp.json                  # машинная копия ICP (criteria ids, exclusions, search plan) для скрипта и агентов
```

- [ ] **Step 5: Проверка**

Run: `./test.sh 2>&1 | grep -E 'icp-builder|FAIL'`
Expected: `ok skills/icp-builder/SKILL.md`, без FAIL по этому файлу. Дополнительно: `python3 -c 'import json; json.load(open("skills/icp-builder/icp-example.json"))'` → без ошибок.

- [ ] **Step 6: Commit**

```bash
git add skills/icp-builder docs/superpowers/specs
git commit -m "feat: icp-builder skill with brief template and icp.json schema"
```

---

### Task 4: `leadgen.py score` — merge и детерминированный скоринг

**Files:**
- Create: `skills/deep-research/scripts/leadgen.py`
- Create: `skills/deep-research/scripts/test_leadgen.py`

**Interfaces:**
- Consumes: `leads/<slug>/icp.json` (Task 3), `leads/<slug>/research/<channel>.json` — массив объектов:

```json
{"company": "str", "domain": "str", "country": "str",
 "website": "url|null", "linkedin": "url|null", "instagram": "url|null", "facebook": "url|null",
 "google_maps": "url|null", "reviews": "url|null", "why": "1 line",
 "evidence": [{"criterion": "M1|N1|T1", "found": true, "url": "str", "note": "str", "date": "YYYY-MM|null"}],
 "public_contacts": [{"type": "phone|email|form", "value": "str", "source": "website|google_maps|linkedin|directory:<name>|...", "source_url": "str"}]}
```
- Produces: `leads/<slug>/research/scored.json` — тот же объект + `score:int`, `channels:[str]`, отсортирован по score desc, обрезан до `ceil(N*1.3)`. CLI: `python3 leadgen.py score <icp_dir> --n 40`.

- [ ] **Step 1: Тест для `score`**

`skills/deep-research/scripts/test_leadgen.py`:
```python
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
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 skills/deep-research/scripts/test_leadgen.py`
Expected: `AssertionError` с stderr `can't open file ... leadgen.py`.

- [ ] **Step 3: Реализация `score`**

`skills/deep-research/scripts/leadgen.py`:
```python
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
```

- [ ] **Step 4: Запустить тест**

Run: `python3 skills/deep-research/scripts/test_leadgen.py`
Expected: `test_score ok`. Если падает на `beta.com` score: проверка — Beta имеет M1, M2 (60) + N1 из 2 nice (12.5) + T1 устаревший (0) = 72.5 → `round` даёт 72 (banker's rounding в Python: `round(72.5)` = 72). Assert `60 + 12` = 72 — верно.

- [ ] **Step 5: Commit**

```bash
git add skills/deep-research/scripts
git commit -m "feat: leadgen.py score — merge by domain, exclusions, 60/25/15 scoring"
```

---

### Task 5: `leadgen.py tables` — две выходные таблицы

**Files:**
- Modify: `skills/deep-research/scripts/leadgen.py` (добавить `cmd_tables` и хелперы перед `main`)
- Modify: `skills/deep-research/scripts/test_leadgen.py` (добавить `test_tables`)

**Interfaces:**
- Consumes: `research/scored.json` (Task 4); `research/verified.json` — массив `{"domain": str, "status": "confirmed|rejected|unverifiable", "checked": [{"criterion": str, "confirmed": bool, "url": str}], "reason": str}`; `research/contacts.json` — массив `{"domain": str, "company": str, "people": [{"name": str, "title": str, "role": "decision-maker|influencer|blocker", "profile_url": str, "contacts": [{"type": "email|phone|linkedin|telegram|other", "value": str, "source": str, "source_url": str}]}]}`.
- Produces: `leads/<slug>/companies-<date>.md|.csv`, `leads/<slug>/people-<date>.md|.csv`. CLI: `python3 leadgen.py tables <icp_dir> --n 40 --date 2026-09-08`.

- [ ] **Step 1: Тест для `tables`**

Добавить в `test_leadgen.py` перед `if __name__`:
```python
def test_tables():
    d = setup()
    (d / "research" / "scored.json").write_text(json.dumps([
        {"company": "Alpha", "domain": "alpha.com", "website": "https://alpha.com", "linkedin": None, "score": 100,
         "why": "fits all", "channels": ["registries"],
         "evidence": [{"criterion": "T1", "found": True, "url": "https://jobs/1", "date": "2026-08"}],
         "public_contacts": [{"type": "phone", "value": "+1 555", "source": "website", "source_url": "https://alpha.com"},
                             {"type": "email", "value": "info@alpha.com", "source": None, "source_url": "https://maps.google.com/x"}]},
        {"company": "Beta", "domain": "beta.com", "score": 72, "evidence": [], "public_contacts": [], "channels": []},
        {"company": "Gamma", "domain": "gamma.com", "score": 72, "evidence": [], "public_contacts": [], "channels": []},
    ]))
    (d / "research" / "verified.json").write_text(json.dumps([
        {"domain": "alpha.com", "status": "confirmed", "checked": [], "reason": ""},
        {"domain": "beta.com", "status": "rejected", "checked": [], "reason": "retail only"},
    ]))
    (d / "research" / "contacts.json").write_text(json.dumps([
        {"domain": "www.alpha.com", "company": "Alpha", "people": [
            {"name": "Ann Lee", "title": "Procurement Manager", "role": "decision-maker",
             "profile_url": "https://linkedin.com/in/ann",
             "contacts": [{"type": "email", "value": "ann@alpha.com", "source": "hunter", "source_url": "https://hunter.io"}]},
            {"name": "Bob Ray", "title": "CFO", "role": "blocker", "profile_url": "https://alpha.com/team", "contacts": []}]},
    ]))
    out = run("tables", str(d), "--n", "2", "--date", "2026-09-08")
    assert "companies=2 people=2" in out, out
    md = (d / "companies-2026-09-08.md").read_text()
    assert "| Beta |" not in md and "| Gamma |" in md          # rejected dropped, unverifiable kept
    assert "+1 555_website; info@alpha.com_maps.google.com" in md
    assert "hiring (https://jobs/1)" in md and "| confirmed |" in md and "| unverifiable |" in md
    rows = list(__import__("csv").reader(open(d / "companies-2026-09-08.csv")))
    assert rows[0][0] == "#" and len(rows) == 3 and rows[1][1] == "Alpha"
    pmd = (d / "people-2026-09-08.md").read_text()
    assert "| Ann Lee | Procurement Manager | decision-maker | ann@alpha.com_hunter |" in pmd
    assert "| Bob Ray | CFO | blocker | — |" in pmd
    shutil.rmtree(d)
    print("test_tables ok")
```
и в блок `__main__` добавить `test_tables()` после `test_score()`.

- [ ] **Step 2: Запустить — падает**

Run: `python3 skills/deep-research/scripts/test_leadgen.py`
Expected: `test_score ok`, затем `NameError: name 'cmd_tables' is not defined` (в stderr subprocess → AssertionError).

- [ ] **Step 3: Реализация `tables`**

Вставить в `leadgen.py` перед `def main():`:
```python
COMPANY_HEADERS = ["#", "Company", "Website", "LinkedIn", "Instagram", "Facebook", "Google Maps", "Reviews",
                   "Score", "Verification", "Triggers (source URL)", "Public contacts", "Why it fits"]
PEOPLE_HEADERS = ["#", "Company", "Name", "Title", "Role", "Contacts", "Profile source"]


def fmt_contacts(items):
    """value_source; value_source — source label falls back to the source_url host."""
    parts = [f"{c['value']}_{c.get('source') or norm_domain(c.get('source_url')) or 'unknown'}"
             for c in items or [] if c.get("value")]
    return "; ".join(parts) or "—"


def md_table(headers, rows):
    esc = lambda v: ("—" if v in (None, "", []) else str(v)).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(esc(v) for v in r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def write_both(base, headers, rows):
    Path(str(base) + ".md").write_text(md_table(headers, rows))
    with open(str(base) + ".csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows([["" if v is None else v for v in r] for r in rows])


def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def cmd_tables(d, n, day):
    icp = json.loads((d / "icp.json").read_text())
    r = d / "research"
    scored = load_json(r / "scored.json", [])
    verified = {norm_domain(v["domain"]): v for v in load_json(r / "verified.json", [])}
    contacts = load_json(r / "contacts.json", [])
    trig = {t["id"]: t["text"] for t in icp.get("triggers") or []}

    kept = [c for c in scored if verified.get(c["domain"], {}).get("status") != "rejected"][:n]
    rows = []
    for i, c in enumerate(kept, 1):
        v = verified.get(c["domain"], {})
        trs = "; ".join(f"{trig.get(e['criterion'], e['criterion'])} ({e.get('url')})"
                        for e in c.get("evidence") or [] if e.get("found") and e.get("criterion") in trig)
        rows.append([i, c.get("company"), c.get("website"), c.get("linkedin"), c.get("instagram"), c.get("facebook"),
                     c.get("google_maps"), c.get("reviews"), c.get("score"), v.get("status", "unverifiable"),
                     trs, fmt_contacts(c.get("public_contacts")), c.get("why") or v.get("reason")])
    write_both(d / f"companies-{day}", COMPANY_HEADERS, rows)

    order = {c["domain"]: i for i, c in enumerate(kept)}
    entries = [e for e in contacts if norm_domain(e.get("domain")) in order]
    entries.sort(key=lambda e: order[norm_domain(e["domain"])])
    prows = []
    for e in entries:
        for p in e.get("people") or []:
            prows.append([len(prows) + 1, e.get("company"), p.get("name"), p.get("title"), p.get("role"),
                          fmt_contacts(p.get("contacts")), p.get("profile_url")])
    write_both(d / f"people-{day}", PEOPLE_HEADERS, prows)
    print(f"companies={len(rows)} people={len(prows)}")
```

- [ ] **Step 4: Запустить тесты**

Run: `python3 skills/deep-research/scripts/test_leadgen.py && ./test.sh`
Expected: `test_score ok`, `test_tables ok`; `./test.sh` — `ok leadgen.py`, падает только на отсутствующем `skills/deep-research/SKILL.md` (Task 7).

- [ ] **Step 5: Commit**

```bash
git add skills/deep-research/scripts
git commit -m "feat: leadgen.py tables — companies and people md/csv with value_source contacts"
```

---

### Task 6: Шаблоны промптов для subagent'ов

**Files:**
- Create: `skills/deep-research/prompts/channel.md`
- Create: `skills/deep-research/prompts/verifier.md`
- Create: `skills/deep-research/prompts/contacts.md`

**Interfaces:**
- Consumes: JSON-схемы из Task 4/5 Interfaces.
- Produces: три шаблона с плейсхолдерами `{{...}}`, которые оркестратор (Task 7) заполняет и передаёт в `Agent(prompt=...)`. Плейсхолдеры: `{{ICP_BLOCK}}`, `{{EXCLUSIONS}}`, `{{CHANNEL}}`, `{{SOURCES}}`, `{{QUERIES}}`, `{{LANGUAGES}}`, `{{REGION_OR_SEGMENT}}`, `{{SEARCH_BUDGET}}`, `{{SCRAPE_BUDGET}}`, `{{EXTRA_SOURCES}}`, `{{OUTPUT_PATH}}`, `{{COMPANIES_JSON}}`, `{{MUST_HAVE_LIST}}`, `{{DECISION_MAKERS}}`.

- [ ] **Step 1: Промпт агента-канала**

`skills/deep-research/prompts/channel.md`:
```markdown
You are a B2B research agent. Find real, currently operating companies matching the ICP below, using ONLY the search channel assigned to you. Collect evidence, not opinions. Write results as JSON to the given path and reply with a two-line summary (count found, anything degraded).

# ICP
{{ICP_BLOCK}}

# Exclude (never report these)
{{EXCLUSIONS}}

# Your channel: {{CHANNEL}}
Sources to use: {{SOURCES}}
Scope: {{REGION_OR_SEGMENT}}
Query patterns (run in {{LANGUAGES}}; adapt and add your own):
{{QUERIES}}

# Tools
- Prefer the Firecrawl skills via the Skill tool: `firecrawl-search` for discovery, `firecrawl-scrape` for a company page, `firecrawl-company-directories` for directory pages, `firecrawl-lead-gen` when a prospect database fits your channel.
- Extra sources the user has access to (use if relevant to your channel): {{EXTRA_SOURCES}}
- Fallback: WebSearch / WebFetch. If Firecrawl fails or is rate-limited, switch to fallback and set `"degraded": true` on every record you produce afterwards.
- Budget: at most {{SEARCH_BUDGET}} searches and {{SCRAPE_BUDGET}} page fetches in total. Stop when exhausted and write what you have.

# Rules
- Real companies only. No guesses, no "likely" entries. If you cannot find a source URL for a fact, do not record the fact.
- Do NOT score. Record which criteria you could confirm, with the URL where you saw it.
- For triggers include `"date": "YYYY-MM"` when the source shows one, else `null`.
- Public contacts of the COMPANY only (phone, email, contact form) — with a `source` label (`website`, `google_maps`, `linkedin`, `facebook`, `directory:<name>`) and `source_url`. No personal contacts here.
- Quality over quantity: 8 verified companies beat 30 maybes.

# Output
Write a JSON array to `{{OUTPUT_PATH}}` (Write tool). Empty array `[]` if nothing found — that is acceptable. Schema per record:

```json
{"company": "str", "domain": "example.com", "country": "str",
 "website": "url|null", "linkedin": "url|null", "instagram": "url|null", "facebook": "url|null",
 "google_maps": "url|null", "reviews": "url|null", "why": "one line why it fits",
 "degraded": false,
 "evidence": [{"criterion": "M1|N1|T1 (ids from the ICP)", "found": true, "url": "str", "note": "str", "date": "YYYY-MM|null"}],
 "public_contacts": [{"type": "phone|email|form", "value": "str", "source": "str", "source_url": "str"}]}
```
```

- [ ] **Step 2: Промпт verifier'а**

`skills/deep-research/prompts/verifier.md`:
```markdown
You are a verification agent. For each company below, open its website (and the evidence URLs if the website is not enough) and confirm or reject every must-have criterion. You are the last line of defence against hallucinated leads: be strict.

# Must-have criteria
{{MUST_HAVE_LIST}}

# Companies to verify
{{COMPANIES_JSON}}

# Tools
- `firecrawl-scrape` via the Skill tool, or WebFetch as fallback. At most 3 page fetches per company.

# Rules
- `confirmed` — every must-have is visible on the company's own site or an authoritative source you opened yourself.
- `rejected` — at least one must-have is contradicted (e.g. retail only, different country, company closed) or the company does not exist.
- `unverifiable` — site unreachable / no evidence either way. Do not reject for lack of evidence.
- One line `reason` per company.

# Output
Write a JSON array to `{{OUTPUT_PATH}}` (Write tool). Reply with counts of confirmed / rejected / unverifiable.

```json
{"domain": "example.com", "status": "confirmed|rejected|unverifiable",
 "checked": [{"criterion": "M1", "confirmed": true, "url": "str"}], "reason": "one line"}
```
```

- [ ] **Step 3: Промпт агента контактов**

`skills/deep-research/prompts/contacts.md`:
```markdown
You are a contact-enrichment agent. For each company below find the people who match the decision-maker titles from the ICP and their PUBLIC contact details. Only public data with a source URL.

# Decision-maker titles (from the ICP)
{{DECISION_MAKERS}}

# Companies
{{COMPANIES_JSON}}

# Where to look
- LinkedIn (people search: title + company), the company website (team / about / contacts pages), press releases, industry directories, conference speaker lists, local business registries listing directors.
- Extra sources the user has access to: {{EXTRA_SOURCES}} — use them first for emails/phones when available.
- Tools: `firecrawl-search`, `firecrawl-scrape`, `firecrawl-lead-research` via the Skill tool; WebSearch/WebFetch as fallback. Budget: {{SEARCH_BUDGET}} searches, {{SCRAPE_BUDGET}} fetches in total.

# Rules
- 1–3 people per company, prioritising `decision-maker` roles, then `influencer`, then `blocker`.
- A person with name + title + LinkedIn URL and no email/phone is still a valid record — keep them with `"contacts": []`.
- Never guess emails from patterns unless a source (Hunter, Apollo, the website) shows that exact address. Never fabricate phones.
- Each contact carries `source` (`linkedin`, `website`, `hunter`, `apollo`, `press`, `directory:<name>`, ...) and `source_url`.
- `profile_url` — the page where the person is shown in that role at that company.

# Output
Write a JSON array to `{{OUTPUT_PATH}}` (Write tool). Reply with counts of people and contacts found.

```json
{"domain": "example.com", "company": "str",
 "people": [{"name": "str", "title": "str", "role": "decision-maker|influencer|blocker", "profile_url": "str",
             "contacts": [{"type": "email|phone|linkedin|telegram|other", "value": "str", "source": "str", "source_url": "str"}]}]}
```
```

- [ ] **Step 4: Проверить, что плейсхолдеры согласованы**

Run: `grep -oh '{{[A-Z_]*}}' skills/deep-research/prompts/*.md | sort -u`
Expected ровно этот список: `{{CHANNEL}} {{COMPANIES_JSON}} {{DECISION_MAKERS}} {{EXCLUSIONS}} {{EXTRA_SOURCES}} {{ICP_BLOCK}} {{LANGUAGES}} {{MUST_HAVE_LIST}} {{OUTPUT_PATH}} {{QUERIES}} {{REGION_OR_SEGMENT}} {{SCRAPE_BUDGET}} {{SEARCH_BUDGET}} {{SOURCES}}`.

- [ ] **Step 5: Commit**

```bash
git add skills/deep-research/prompts
git commit -m "feat: subagent prompt templates for channel, verifier and contacts"
```

---

### Task 7: Скилл `deep-research` (оркестратор)

**Files:**
- Create: `skills/deep-research/SKILL.md`

**Interfaces:**
- Consumes: `leads/<slug>/icp.json` (Task 3), `prompts/*.md` (Task 6), `scripts/leadgen.py` (Task 4/5).
- Produces: `leads/<slug>/companies-<date>.md|.csv`, `leads/<slug>/people-<date>.md|.csv`, плюс summary-секция в конце `companies-<date>.md`.

- [ ] **Step 1: SKILL.md**

`skills/deep-research/SKILL.md`:
```markdown
---
name: deep-research
description: Orchestrate parallel research agents to find, verify and contact-enrich companies matching an ICP built by icp-builder; outputs companies-*.md/.csv and people-*.md/.csv in leads/<slug>/. Use after an ICP exists or when the user asks to find leads / companies / decision-makers for a known ICP.
---

# Deep Research Orchestrator

You orchestrate; subagents search. You never search the web yourself in this skill. All paths below are relative to the user's current working directory; `SKILL_DIR` is this skill's base directory (announced when the skill loaded) — prompts live in `SKILL_DIR/prompts/`, the script in `SKILL_DIR/scripts/leadgen.py`.

## Step 0 — Locate the ICP and pre-flight

1. Find `leads/*/icp.json`. If none: tell the user to run `/lead-gen` first and stop. If several and no slug was given: ask which one (options = slugs).
2. Read `leads/<slug>/icp.json` into memory. Let `N = icp.n` (default 40).
3. One AskUserQuestion with up to 3 questions:
   - **Firecrawl:** "Paid API key configured" / "Free hosted tier (default)". Sets budgets: free → 15 search / 20 scrape per channel agent; paid → 45 / 60.
   - **Extra sources you have access to** (multiSelect): Apollo, Hunter, LinkedIn Sales Navigator, industry database (name it), none.
   - **How many companies:** `N` (recommended) / 20 / 60 / 100.
4. Create `leads/<slug>/research/` if missing. If it already contains `<channel>.json` files, ask: reuse them (skip Step 2) or re-run.

## Step 1 — Channels

Take `icp.search_plan`. One agent per channel. If `N > 50`, split each channel additionally by country/region or sub-segment from `icp.geography` / `icp.segment` so that no agent is asked for more than ~25 companies; output file then becomes `research/<channel>-<region>.json`. Tell the user the plan in one line: `5 channels × 1 region → 5 agents, budget 15/20 each`.

## Step 2 — Parallel collection

Read `SKILL_DIR/prompts/channel.md`. For each agent fill every `{{PLACEHOLDER}}`:
- `ICP_BLOCK` — the ICP fields (offer, segment, firmographics, geography, core_pain, must_have, nice_to_have, triggers, disqualifiers) rendered as a compact markdown list **including the ids** M1/N1/T1.
- `EXCLUSIONS` — `icp.exclusions` as `name (domain)` lines, or `none`.
- `CHANNEL`, `SOURCES`, `QUERIES` — from the search_plan entry; `LANGUAGES` — `icp.geography.languages`; `REGION_OR_SEGMENT` — the split scope or `all of <countries>`.
- `SEARCH_BUDGET`, `SCRAPE_BUDGET` — from pre-flight; `EXTRA_SOURCES` — chosen extras or `none`.
- `OUTPUT_PATH` — absolute path to `leads/<slug>/research/<channel>[-<region>].json`.

Launch **all** agents in a single message (one `Agent` call per agent, `subagent_type: "general-purpose"`, description `research:<channel>`). Wait for all to finish. Do not read their JSON into your context — the script does that.

## Step 3 — Merge and score

Run: `python3 SKILL_DIR/scripts/leadgen.py score leads/<slug> --n N`
Report the printed line (`raw= merged= scored= kept=`). If `kept=0`: tell the user which channels returned empty / degraded (agents' summaries) and offer to re-run with a wider ICP or bigger budget; stop.

## Step 4 — Verifier pass

Read `leads/<slug>/research/scored.json` **only to split it into batches of ~10 companies** (company, domain, website, evidence URLs — strip contacts to save context). Read `SKILL_DIR/prompts/verifier.md`, fill `MUST_HAVE_LIST` (ids + text), `COMPANIES_JSON` (the batch), `OUTPUT_PATH` = `leads/<slug>/research/verified-<batch>.json`. Launch all batches in parallel (`description: verify:<batch>`). Then concatenate all `verified-*.json` arrays into `leads/<slug>/research/verified.json` (Bash one-liner: `python3 -c 'import json,glob;json.dump(sum((json.load(open(f)) for f in sorted(glob.glob("leads/<slug>/research/verified-*.json"))),[]),open("leads/<slug>/research/verified.json","w"))'`) and delete the batch files.

## Step 5 — Contact enrichment

Take companies from `scored.json` whose verified status is not `rejected`, top `N`. Batches of ~8. Read `SKILL_DIR/prompts/contacts.md`, fill `DECISION_MAKERS` (title — role lines from `icp.decision_makers`), `COMPANIES_JSON` (company, domain, website, linkedin only), `EXTRA_SOURCES`, budgets (same as channel agents), `OUTPUT_PATH` = `leads/<slug>/research/contacts-<batch>.json`. Launch all batches in parallel (`description: contacts:<batch>`). Concatenate into `research/contacts.json` the same way as Step 4 and delete batch files.

## Step 6 — Tables and summary

1. Run: `python3 SKILL_DIR/scripts/leadgen.py tables leads/<slug> --n N --date <today YYYY-MM-DD>`. Report the printed line.
2. Append to `leads/<slug>/companies-<date>.md` a section:

   ```
   ## Notes
   - Hardest criteria to verify: ...
   - Channels that produced most / least: ... (from agents' summaries and `channels` field)
   - Degraded runs (Firecrawl fallback): yes/no, which channels
   - How to sharpen the ICP next time: 2–3 bullets
   ```
3. Tell the user: both file paths, counts (companies, people, contacts), and the notes in 3–5 lines. If `people` is 0, say so explicitly and suggest adding Apollo/Hunter/Sales Navigator access.

## Rules

- Never fabricate rows. If the script output says 0, the answer is 0.
- Never run more than ~12 agents at once; queue extra batches in a second wave.
- Do not paste large JSON into chat; refer to files.
- Contacts everywhere are `value_source` separated by `; ` — the script enforces this, do not reformat.
```

- [ ] **Step 2: Проверка структуры**

Run: `./test.sh`
Expected: все строки `ok ...`, `ok leadgen.py`, `ALL OK`.

- [ ] **Step 3: Commit**

```bash
git add skills/deep-research/SKILL.md
git commit -m "feat: deep-research orchestrator skill"
```

---

### Task 8: Ручной сквозной прогон и фиксация результата

**Files:**
- Modify: `README.md` (секция «Smoke test»)

**Interfaces:**
- Consumes: всё выше.

- [ ] **Step 1: Проверить, что плагин загружается**

Run (из любой пустой тестовой папки, например scratchpad):
```bash
cd "$(mktemp -d)" && claude --plugin-dir ~/Documents/lead-gen-plugin -p 'List the skills available to you that start with "lead-gen:" — names only.'
```
Expected: в ответе упомянуты `lead-gen:icp-builder` и `lead-gen:deep-research`. Если нет — проверить `claude plugin details ~/Documents/lead-gen-plugin` и frontmatter.

- [ ] **Step 2: Интерактивный E2E**

Run: `cd "$(mktemp -d)" && claude --plugin-dir ~/Documents/lead-gen-plugin`, затем ввести `/lead-gen`. Пройти интервью на любом реальном оффере (можно взять пример из `icp-example.json`), сказать `go`, подтвердить запуск research с N=20 и бесплатным тиром.

Чеклист (каждый пункт — да/нет):
- [ ] `leads/<slug>/icp-brief.md` содержит секции ICP, `## Exclusion list`, `## Search plan`; `icp.json` парсится и ids совпадают с брифом.
- [ ] Агенты-каналы запущены одним сообщением параллельно; в `research/` появились `<channel>.json`.
- [ ] `leadgen.py score` напечатал `kept > 0`.
- [ ] `verified.json` и `contacts.json` созданы, батч-файлы удалены.
- [ ] `companies-<date>.md/.csv` и `people-<date>.md/.csv` существуют; в `companies` нет компаний из exclusion list; статус `rejected` отсутствует в таблице; контакты в формате `value_source`.
- [ ] Хотя бы 3 случайных source URL из таблицы открываются и подтверждают факт.
- [ ] Секция `## Notes` дописана в конец `companies-<date>.md`.

- [ ] **Step 3: Зафиксировать процедуру в README**

Добавить в конец `README.md`:
```markdown
## Smoke test

```bash
./test.sh
cd "$(mktemp -d)" && claude --plugin-dir /path/to/lead-gen-plugin
# > /lead-gen  → interview → go → run research (N=20, free tier)
# expect: leads/<slug>/{icp-brief.md,icp.json,research/*.json,companies-<date>.{md,csv},people-<date>.{md,csv}}
```
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: smoke test procedure"
```

Если в E2E что-то из чеклиста не выполнилось — это баг конкретного SKILL.md/промпта; исправлять точечно в соответствующем файле, повторять только упавший шаг, коммитить отдельно (`fix: ...`).
