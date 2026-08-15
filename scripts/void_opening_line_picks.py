"""Anula picks tomados sobre LINEAS DE APERTURA (partidos a >72h vista).

Contexto (15-Ago-2026): las casas listan la NBA con meses de antelacion y el
sistema genero 14 picks shadow sobre lineas de apertura de octubre-diciembre.
Ese "edge" no es el regimen calibrado (la sharp aun no ha afinado la linea) y
ademas el guard de conflicto impediria re-pickear el partido cerca del tipoff.
El fix de raiz es PICK_MAX_HOURS_AHEAD en value_calculator.generate_picks();
este script limpia los picks ya creados: los marca void (misma semantica que
score_resolver) y etiqueta shadow_reasons con 'opening_line_void'.

Uso (en el VPS):
  cd /opt/SmartOddsBasketball/backend
  venv/bin/python ../scripts/void_opening_line_picks.py           # dry-run
  venv/bin/python ../scripts/void_opening_line_picks.py --apply   # ejecuta
"""
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.database import SessionLocal
from app.models.bet import Pick
from app.models.match import Match
from app.config import settings


def main():
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=settings.PICK_MAX_HOURS_AHEAD)
        picks = db.query(Pick).join(Match, Pick.match_id == Match.id).filter(
            Pick.result.is_(None),
            Match.commence_time > cutoff.replace(tzinfo=None),
        ).all()

        if not picks:
            print("Nada que anular: no hay picks pendientes a "
                  f">{settings.PICK_MAX_HOURS_AHEAD:.0f}h vista.")
            return

        for p in picks:
            m = db.get(Match, p.match_id)
            print(f"void pick #{p.id}  [{m.league}] {m.away_team} @ "
                  f"{m.home_team} ({m.commence_time:%d-%b}) edge={p.edge:.1f}%")
            if apply:
                p.result = "void"
                p.profit_units = 0.0
                p.resolved_at = now
                p.is_active = False
                p.shadow_reasons = (
                    (p.shadow_reasons + ",") if p.shadow_reasons else ""
                ) + "opening_line_void"

        if apply:
            db.commit()
            print(f"\nTotal anulados: {len(picks)}")
        else:
            print(f"\nDRY-RUN: {len(picks)} picks se anularian. "
                  "Ejecutar con --apply para aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
