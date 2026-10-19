#!/usr/bin/env bash
# Vigilante de SmartOdds Basquet: cada 10 min (sin argumentos) y resumen diario (--resumen).
# Crontab (VPS XL):
#   */10 * * * * /opt/SmartOddsBasketball/scripts/vigilante.sh >> /opt/SmartOddsBasketball/logs/vigilante.log 2>&1
#   7 9 * * *    /opt/SmartOddsBasketball/scripts/vigilante.sh --resumen >> /opt/SmartOddsBasketball/logs/vigilante.log 2>&1
cd /opt/SmartOddsBasketball/backend || exit 1
set -a; . /opt/SmartOddsBasketball/.env; set +a
exec ./venv/bin/python ../scripts/vigilante.py "$@"
