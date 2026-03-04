#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8501}"
source .cloudflared/env.sh

exec streamlit run testApp.py --server.address 0.0.0.0 --server.port "$PORT"
