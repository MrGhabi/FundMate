#!/usr/bin/env bash
# Run FundMate pipeline against temp archives by default (safer than /data)
# Usage: tools/run_temp_pipeline.sh YYYY-MM-DD

set -euo pipefail

DATE="${1:-}"    # target date is required
if [[ -z "$DATE" ]]; then
  echo "Usage: $0 YYYY-MM-DD" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$PROJECT_ROOT/config/temp.env" ]]; then
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/config/temp.env"
fi

ARCHIVE_DIR="${FUNDMATE_ARCHIVE_DIR:-$PROJECT_ROOT/temp/archives}"
TC_DIR="${FUNDMATE_TC_DIR:-$ARCHIVE_DIR/TC}"

echo "Using archive dir: $ARCHIVE_DIR"
echo "Using TC dir:      $TC_DIR"
echo "Target date:       $DATE"

PYTHONPATH="$PROJECT_ROOT/src" \
  FUNDMATE_OUTPUT_DIR="${FUNDMATE_OUTPUT_DIR:-$PROJECT_ROOT/out}" \
  FUNDMATE_LOG_DIR="${FUNDMATE_LOG_DIR:-$PROJECT_ROOT/log}" \
  python -m src.main "$ARCHIVE_DIR" --date "$DATE" --use-tc --tc-folder "$TC_DIR"
