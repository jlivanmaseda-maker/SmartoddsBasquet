#!/usr/bin/env bash
# Deploy de SmartOdds Basketball al VPS (SCP + systemctl restart, sin git).
# VPS2 (212.227.50.152), la misma que futbol. Backend en puerto 8002.
#
#   bash scripts/deploy.sh backend    # sube backend + reinicia servicio
#   bash scripts/deploy.sh frontend   # build local + sube dist/
#   bash scripts/deploy.sh all        # ambos
set -euo pipefail

VPS="root@212.227.50.152"           # VPS2 — misma maquina que futbol
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"   # misma clave que futbol
REMOTE="/opt/SmartOddsBasketball"
SERVICE="smartodds-basketball-backend"

target="${1:-all}"

deploy_backend() {
  echo "[deploy] backend -> $VPS:$REMOTE/backend"
  scp -i "$SSH_KEY" -r backend/app backend/requirements.txt "$VPS:$REMOTE/backend/"
  ssh -i "$SSH_KEY" "$VPS" "systemctl restart $SERVICE && systemctl status $SERVICE --no-pager | head -5"
}

deploy_frontend() {
  echo "[deploy] building frontend"
  ( cd frontend-react && npm run build )
  echo "[deploy] frontend dist -> $VPS:$REMOTE/frontend-react/dist"
  scp -i "$SSH_KEY" -r frontend-react/dist "$VPS:$REMOTE/frontend-react/"
}

case "$target" in
  backend)  deploy_backend ;;
  frontend) deploy_frontend ;;
  all)      deploy_backend; deploy_frontend ;;
  *) echo "uso: deploy.sh [backend|frontend|all]"; exit 1 ;;
esac
