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
