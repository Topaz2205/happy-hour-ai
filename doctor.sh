#!/usr/bin/env bash
# Check every part of the system and say exactly what is wrong.
#
#   bash doctor.sh
#
# Nothing here changes anything. It reads the state and reports it.
#
# WHY THIS EXISTS
# Every failure this project has had surfaced somewhere other than its cause: a
# stale database column appeared as an error about a budget, a missing schema
# migration appeared as "Load failed" in Safari, an empty API balance appeared
# as a red box in a side panel. Each one was diagnosable in about ten seconds
# once you knew where to look. This looks in all of those places at once.

set -uo pipefail

BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; OFF=$'\033[0m'

PASS=0; WARN=0; FAIL=0
pass() { printf "  ${GRN}✓${OFF} %s\n" "$1"; PASS=$((PASS+1)); }
warn() { printf "  ${YLW}!${OFF} %s\n" "$1"; [ $# -gt 1 ] && printf "      ${DIM}%s${OFF}\n" "$2"; WARN=$((WARN+1)); }
fail() { printf "  ${RED}✗${OFF} %s\n" "$1"; [ $# -gt 1 ] && printf "      ${DIM}%s${OFF}\n" "$2"; FAIL=$((FAIL+1)); }
head() { printf "\n${BOLD}%s${OFF}\n" "$1"; }

cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

# ── 1. The things everything else needs ──────────────────────────────────────
head "Foundations"

[ -d "$ROOT/backend/venv" ] \
  && pass "Python environment" \
  || fail "backend/venv is missing" "bash setup.sh"

if pg_isready -q 2>/dev/null; then
  pass "PostgreSQL is running"
else
  fail "PostgreSQL is not running" "brew services start postgresql@16"
  echo; echo "${RED}Nothing else can be checked until the database is up.${OFF}"; exit 1
fi

export PGPASSWORD=happyhour
db() { psql -U happyhour -h localhost -d happyhour -tAc "$1" 2>/dev/null | tr -d '[:space:]'; }

[ "$(db 'SELECT 1')" = "1" ] \
  && pass "Database reachable" \
  || { fail "cannot connect to the happyhour database" "bash setup.sh"; exit 1; }

cd "$ROOT/backend" || exit 1
# shellcheck disable=SC1091
source venv/bin/activate 2>/dev/null || true

# ── 2. Schema ────────────────────────────────────────────────────────────────
head "Database schema"

CURRENT=$(alembic current 2>/dev/null | tail -1)
HEAD_REV=$(alembic heads 2>/dev/null | tail -1)
if [ -n "$CURRENT" ] && [ "${CURRENT%% *}" = "${HEAD_REV%% *}" ]; then
  pass "migrations at head"
else
  warn "migrations are behind" "cd backend && alembic upgrade head"
fi

# The check that matters more: migrations can report themselves current while a
# column is stale, and that is precisely the failure that is hardest to read.
SCHEMA_OUT=$(python scripts/verify_schema.py --check 2>&1)
if echo "$SCHEMA_OUT" | grep -q "^✓"; then
  pass "columns match the code"
else
  fail "a column is out of step with the code" "cd backend && python scripts/verify_schema.py"
  echo "$SCHEMA_OUT" | sed 's/^/      /'
fi

# ── 3. Data ──────────────────────────────────────────────────────────────────
head "Cocktails and prices"

COCKTAILS=$(db "SELECT count(*) FROM cocktails WHERE active;")
[ "${COCKTAILS:-0}" -gt 0 ] \
  && pass "$COCKTAILS active cocktails" \
  || fail "no cocktails loaded" "bash reset.sh"

COV=$(db "
WITH priced AS (
  SELECT DISTINCT m.ingredient_id FROM ingredient_product_mapping m
  JOIN supplier_products sp ON sp.product_id = m.product_id
  WHERE sp.price_after_vat IS NOT NULL AND sp.available)
SELECT round(100.0 * (SELECT count(*) FROM priced) / NULLIF(count(*),0), 1) FROM ingredients;")

# A partial cost is worse than no cost for someone deciding a budget, so this is
# reported as a real problem rather than a note.
BLOCKERS=$(db "
WITH priced AS (
  SELECT DISTINCT m.ingredient_id FROM ingredient_product_mapping m
  JOIN supplier_products sp ON sp.product_id = m.product_id
  WHERE sp.price_after_vat IS NOT NULL AND sp.available)
SELECT count(DISTINCT i.id) FROM ingredients i
JOIN cocktail_ingredients ci ON ci.ingredient_id = i.id
JOIN cocktails c ON c.id = ci.cocktail_id AND c.active
WHERE i.id NOT IN (SELECT ingredient_id FROM priced);")

if [ "${BLOCKERS:-1}" = "0" ]; then
  pass "every active cocktail can be costed (${COV}% ingredient coverage)"
else
  warn "$BLOCKERS ingredient(s) have no price — those events cost partially" \
       "Open the Mappings page, or run: bash update.sh"
fi

# ── 4. The AI provider ───────────────────────────────────────────────────────
head "AI provider (agent panel only)"

if [ ! -f .env ]; then
  fail "backend/.env is missing" "bash setup.sh"
else
  PROV=$(grep -E '^LLM_PROVIDER=' .env | cut -d= -f2)
  KEYLINE=$(grep -E '^LLM_API_KEY=.+' .env || grep -E '^ANTHROPIC_API_KEY=sk-ant-.+' .env || true)
  if [ -z "$KEYLINE" ]; then
    warn "no provider key set — the agent panel will be unavailable" \
         "bash set-key.sh  (offers free providers)"
  else
    pass "key set for provider '${PROV:-anthropic}'"
    # The only check that proves anything: a real tool call.
    LLM_OUT=$(timeout 45 python scripts/check_llm.py 2>&1)
    if echo "$LLM_OUT" | grep -q "Tool calling works"; then
      pass "$(echo "$LLM_OUT" | grep 'Tool calling works' | sed 's/^✓ //')"
    else
      fail "the provider is not usable" "cd backend && python scripts/check_llm.py"
      # Print whatever the provider actually said. Filtering for a leading ✗
      # dropped the reason entirely when the message was shaped differently —
      # which left the one line that explains the failure invisible.
      echo "$LLM_OUT" | grep -v '^Provider\|^Model\|^Key\|^$\|^Testing' \
        | head -4 | sed 's/^/      /'
    fi
  fi
fi

# ── 5. Are the servers up ────────────────────────────────────────────────────
head "Servers"

if curl -fsS --max-time 4 http://localhost:8000/health >/dev/null 2>&1 \
   || curl -fsS --max-time 4 http://localhost:8000/api/events >/dev/null 2>&1; then
  pass "API on :8000"
else
  warn "API is not running" "cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000"
fi

if curl -fsS --max-time 4 http://localhost:3000 >/dev/null 2>&1; then
  pass "web app on :3000"
else
  warn "web app is not running" "cd frontend && npm run dev"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo
if [ "$FAIL" -gt 0 ]; then
  printf "${RED}${BOLD}%d problem(s)${OFF}, %d warning(s), %d fine.\n" "$FAIL" "$WARN" "$PASS"
  echo "Fix the ✗ lines above first — the commands are underneath each one."
elif [ "$WARN" -gt 0 ]; then
  printf "${YLW}${BOLD}%d thing(s) to look at${OFF}, %d fine.\n" "$WARN" "$PASS"
  echo "Nothing is broken. The ! lines are things that limit what works."
else
  printf "${GRN}${BOLD}All %d checks passed.${OFF} Open http://localhost:3000\n" "$PASS"
fi
echo
