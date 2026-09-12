#!/usr/bin/env bash
#
# Export one workspace from a Railway-hosted PostgreSQL service to JSONL.
#
# Railway databases have no public route by default, so this runs psql inside
# the service over Railway's SSH tunnel and captures stdout locally. Use it
# when scripts/import_from_postgres.py cannot reach the database directly.
#
#   ./scripts/export_via_railway.sh <organization-id> [output-dir] [service]
#
# Each table becomes <output-dir>/<table>.jsonl, one JSON object per line.
# Load the result with:  python -m scripts.import_from_jsonl --source <output-dir>

set -euo pipefail

ORG_ID="${1:?usage: export_via_railway.sh <organization-id> [output-dir] [service]}"
OUT_DIR="${2:-exports}"
SERVICE="${3:-postgres}"
DB_USER="${PGUSER:-meetstream}"
DB_NAME="${PGDATABASE:-meetstream_companion}"

mkdir -p "$OUT_DIR"

# Rows are selected per table; those without their own organization_id are
# reached through the meeting they belong to.
run_export() {
  local table="$1" where="$2"
  local sql="SELECT row_to_json(t)::text FROM (SELECT * FROM ${table} t0 WHERE ${where}) t"

  printf '  %-32s' "$table"
  railway ssh --service "$SERVICE" -- \
    psql -U "$DB_USER" -d "$DB_NAME" -A -t -c "$sql" \
    | grep -E '^\{' > "$OUT_DIR/$table.jsonl" || true

  printf '%6s rows\n' "$(wc -l < "$OUT_DIR/$table.jsonl" | tr -d ' ')"
}

BY_MEETING="t0.meeting_id IN (SELECT id FROM meetings WHERE organization_id='${ORG_ID}')"

echo "Exporting workspace ${ORG_ID} from service '${SERVICE}'"
run_export organizations               "t0.id='${ORG_ID}'"
run_export users                       "t0.organization_id='${ORG_ID}'"
run_export meetings                    "t0.organization_id='${ORG_ID}'"
run_export participants                "${BY_MEETING}"
run_export transcript_segments         "${BY_MEETING}"
run_export memories                    "t0.organization_id='${ORG_ID}'"
run_export action_items                "t0.organization_id='${ORG_ID}'"
run_export meeting_memory_embeddings   "t0.organization_id='${ORG_ID}'"
run_export company_knowledge_embeddings "t0.organization_id='${ORG_ID}'"
run_export processing_jobs             "${BY_MEETING}"

echo
echo "Written to $OUT_DIR/"
