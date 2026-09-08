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
