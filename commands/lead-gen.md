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
