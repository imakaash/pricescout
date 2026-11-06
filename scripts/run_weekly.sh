#!/bin/zsh
# PriceScout weekly pipeline: scrape -> simulate VoltMarkt -> extract -> match -> analyse.
# Run by launchd (see deploy/) or by hand. Logs go to logs/weekly-YYYY-MM-DD.log.
set -u
cd "$(dirname "$0")/.."
PY="${PRICESCOUT_PYTHON:-/opt/anaconda3/envs/pricescout/bin/python}"
mkdir -p logs
LOG="logs/weekly-$(date +%F).log"
exec >>"$LOG" 2>&1
echo "=== PriceScout weekly run $(date)"

step() {  # run a step, log its outcome, keep going if it fails
  echo "--- $1 ($(date +%H:%M))"
  shift
  "$@" || echo "!!! step failed with exit code $?"
}

# Ollama must be up for extraction, rationales and the report.
curl -sf http://localhost:11434/api/tags >/dev/null || brew services start ollama

for r in mediamarkt alternate medimax; do
  step "scrape $r" "$PY" scripts/scrape.py --retailer "$r"
done
step "simulate VoltMarkt" "$PY" scripts/generate_internal_data.py
step "extract attributes" "$PY" scripts/extract_attributes.py --llm-limit 200
if [[ -f training/adapters/matcher/adapters.safetensors ]]; then
  step "match products" "$PY" scripts/train_matcher.py apply
fi
step "weekly analysis" "$PY" scripts/weekly_analysis.py
echo "=== done $(date)"
