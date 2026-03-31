#!/usr/bin/env bash
set -euo pipefail

event_id="${1:-}"

if [[ -n "$event_id" ]]; then
  python3 review_event.py "$event_id"
else
  python3 review_event.py
fi

python3 review_index.py >/dev/null

echo "Indice atualizado em volumes/faces/reviews/index.html"
