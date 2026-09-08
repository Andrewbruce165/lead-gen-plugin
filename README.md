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

## Smoke test

```bash
./test.sh
cd "$(mktemp -d)" && claude --plugin-dir /path/to/lead-gen-plugin
# > /lead-gen  → interview → go → run research (N=20, free tier)
# expect: leads/<slug>/{icp-brief.md,icp.json,research/*.json,companies-<date>.{md,csv},people-<date>.{md,csv}}
```
