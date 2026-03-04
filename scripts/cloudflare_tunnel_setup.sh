#!/usr/bin/env bash
set -euo pipefail

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "[ERROR] cloudflared 未安装。请先执行: brew install cloudflared" >&2
  exit 1
fi

if [ $# -lt 1 ]; then
  echo "用法: $0 <hostname> [local_port] [tunnel_name]" >&2
  echo "示例: $0 app.example.com 8501 investment-app" >&2
  exit 1
fi

HOSTNAME="$1"
LOCAL_PORT="${2:-8501}"
TUNNEL_NAME="${3:-investment-app}"
CERT_PATH="${HOME}/.cloudflared/cert.pem"

if [ ! -f "$CERT_PATH" ]; then
  echo "[ERROR] 未检测到 ${CERT_PATH}。请先执行: cloudflared tunnel login" >&2
  exit 1
fi

echo "[INFO] 确认隧道存在: ${TUNNEL_NAME}"
if ! cloudflared tunnel info "$TUNNEL_NAME" >/dev/null 2>&1; then
  cloudflared tunnel create "$TUNNEL_NAME"
fi

TUNNEL_ID="$(cloudflared tunnel list --output json | python -c 'import json,sys;name=sys.argv[1];data=json.load(sys.stdin);print(next((x["id"] for x in data if x.get("name")==name),""))' "$TUNNEL_NAME")"

if [ -z "$TUNNEL_ID" ]; then
  echo "[ERROR] 无法获取 Tunnel ID" >&2
  exit 1
fi

CRED_FILE="${HOME}/.cloudflared/${TUNNEL_ID}.json"
if [ ! -f "$CRED_FILE" ]; then
  echo "[ERROR] 未找到隧道凭证: ${CRED_FILE}" >&2
  exit 1
fi

echo "[INFO] 绑定 DNS: ${HOSTNAME} -> ${TUNNEL_NAME}"
cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME"

mkdir -p .cloudflared
cat > .cloudflared/config.yml <<YAML
tunnel: ${TUNNEL_ID}
credentials-file: ${CRED_FILE}

ingress:
  - hostname: ${HOSTNAME}
    service: http://localhost:${LOCAL_PORT}
  - service: http_status:404
YAML

cat > .cloudflared/env.sh <<ENV
export WEBAUTHN_RP_ID=${HOSTNAME}
export WEBAUTHN_ORIGIN=https://${HOSTNAME}
export WEBAUTHN_RP_NAME='Investment App'
ENV

echo "[OK] Tunnel 配置完成"
echo "[NEXT] 启动应用: source .cloudflared/env.sh && streamlit run testApp.py --server.address 0.0.0.0 --server.port ${LOCAL_PORT}"
echo "[NEXT] 启动隧道: cloudflared tunnel --config .cloudflared/config.yml run ${TUNNEL_NAME}"
