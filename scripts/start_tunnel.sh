#!/usr/bin/env bash
set -euo pipefail

TUNNEL_NAME="${1:-investment-app}"
exec cloudflared tunnel --config .cloudflared/config.yml run "$TUNNEL_NAME"
