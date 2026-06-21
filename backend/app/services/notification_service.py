"""Notification Service para Basket (Telegram).

Portado de tenis, adaptado a deporte de equipo:
- Equipos en vez de jugadores; liga en vez de superficie; puntos en vez de games.
- Fire-and-forget: los errores NUNCA bloquean el flujo principal.
- Los picks SHADOW no notifican (no se muestran al usuario).
- v1: envia al chat de sistema (TELEGRAM_CHAT_ID). El fan-out por suscriptor se
  anadira cuando exista el sistema de usuarios/suscripciones.
"""
import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models.match import Match
from app.models.bet import Pick

logger = logging.getLogger("smartodds_basketball.notifications")

LEAGUE_EMOJI = {
    "nba": "\U0001f3c0",        # 🏀
    "wnba": "\U0001f3c0",
    "ncaab": "\U0001f3c0",
    "euroleague": "\U0001f3c0",
    "nbl": "\U0001f3c0",
}


def _configured() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)


def send_new_pick(pick: Pick, match: Match):
    """Notifica un nuevo pick (solo si NO es shadow)."""
    if not _configured() or pick.is_shadow:
        return
    try:
        _send_telegram(_format_new_pick(pick, match))
    except Exception as e:
        logger.error(f"Error enviando pick Telegram: {e}")


def send_result(pick: Pick, match: Match):
    """Notifica el resultado de un pick (solo si NO es shadow)."""
    if not _configured() or pick.is_shadow:
        return
    try:
        _send_telegram(_format_result(pick, match))
    except Exception as e:
        logger.error(f"Error enviando resultado Telegram: {e}")


def send_daily_summary(stats: dict):
    if not _configured():
        return
    try:
        _send_telegram(_format_daily_summary(stats))
    except Exception as e:
        logger.error(f"Error enviando resumen Telegram: {e}")


def send_test(text: str = "Bot de SmartOdds Basket conectado correctamente."):
    """Mensaje de prueba para validar la configuracion del bot."""
    if not _configured():
        return False
    return _send_telegram(f"\U0001f3c0 {text}")


# ──────────────────────────────────────────────────────────────
# Formatters
# ──────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """Escape MarkdownV2."""
    if not text:
        return ""
    for ch in ("_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        text = text.replace(ch, f"\\{ch}")
    return text


def _pick_label(pick: Pick, match: Match) -> str:
    bt = pick.bet_type or "?"
    if bt == "match_winner_home":
        return f"Ganador: {match.home_team}"
    if bt == "match_winner_away":
        return f"Ganador: {match.away_team}"
    if bt.startswith("spread_home_"):
        return f"Hándicap {match.home_team} {bt.replace('spread_home_', '')}"
    if bt.startswith("spread_away_"):
        return f"Hándicap {match.away_team} {bt.replace('spread_away_', '')}"
    if bt.startswith("total_points_over_"):
        return f"Más de {bt.replace('total_points_over_', '')} puntos"
    if bt.startswith("total_points_under_"):
        return f"Menos de {bt.replace('total_points_under_', '')} puntos"
    return bt


def _format_new_pick(pick: Pick, match: Match) -> str:
    emoji = LEAGUE_EMOJI.get(match.league_tier or "", "\U0001f3c0")
    edge = pick.edge or 0
    edge_emoji = "\U0001f7e2" if edge >= 8 else "\U0001f7e1" if edge >= 4 else "\U0001f7e0"

    stake = _calc_stake(pick)
    stake_str = f"{stake:.2f}" if stake > 0 else "—"
    prob_pct = f"{pick.estimated_probability * 100:.1f}" if pick.estimated_probability else "?"

    if match.commence_time:
        ct = match.commence_time
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)
        match_date = ct.strftime("%d/%m %H:%M")
    else:
        match_date = "?"

    lines = [
        f"{emoji} *NUEVO PICK DE VALOR*",
        "",
        f"{emoji} *{_esc(match.home_team)} vs {_esc(match.away_team)}*",
        f"\U0001f3c6 {_esc(match.league or match.league_tier or '?')}",
        f"\U0001f4c5 {match_date} UTC",
        "",
        f"\U0001f3af *Apuesta:* {_esc(_pick_label(pick, match))}",
        f"\U0001f4ca *Cuota:* {pick.best_odds:.2f} @ {_esc(pick.best_bookmaker or '?')}",
        f"{edge_emoji} *Edge:* \\+{edge:.1f}%",
        f"\U0001f4b0 *Stake:* {stake_str} EUR",
        f"\U0001f4cd *Prob:* {prob_pct}%",
        "",
        "\\#SmartOddsBasket \\#ValueBetting",
    ]
    return "\n".join(lines)


def _format_result(pick: Pick, match: Match) -> str:
    result = (pick.result or "").lower()
    result_emoji = {"won": "✅", "lost": "❌", "void": "⬜"}.get(result, "❓")
    result_label = {"won": "GANADO", "lost": "PERDIDO", "void": "VOID"}.get(result, "?")

    profit = pick.profit_units or 0
    profit_sign = "+" if profit >= 0 else ""
    profit_emoji = "\U0001f4b0" if profit > 0 else "\U0001f4c9" if profit < 0 else "➖"

    clv_str = ""
    if pick.clv_pct is not None:
        clv_sign = "+" if pick.clv_pct >= 0 else ""
        clv_emoji = "\U0001f7e2" if pick.clv_pct > 0 else "\U0001f534"
        clv_str = f"{clv_emoji} *CLV:* {clv_sign}{pick.clv_pct:.1f}%"

    lines = [
        f"{result_emoji} *RESULTADO \\- {result_label}*",
        "",
        f"\U0001f3c0 *{_esc(match.home_team)} vs {_esc(match.away_team)}*",
        f"\U0001f4cb *Score:* {_esc(match.score or '?')}",
        f"\U0001f3c6 {_esc(match.league or '?')}",
        "",
        f"\U0001f3af *Apuesta:* {_esc(_pick_label(pick, match))}",
        f"\U0001f4ca *Cuota:* {pick.best_odds:.2f} @ {_esc(pick.best_bookmaker or '?')}",
        f"{profit_emoji} *Profit:* {profit_sign}{profit:.2f}u",
    ]
    if clv_str:
        lines.append(clv_str)
    lines.extend(["", "\\#SmartOddsBasket \\#Resultado"])
    return "\n".join(lines)


def _format_daily_summary(stats: dict) -> str:
    won = stats.get("won", 0)
    lost = stats.get("lost", 0)
    void = stats.get("void", 0)
    profit = stats.get("profit", 0.0)
    total_profit = stats.get("total_profit", 0.0)
    winrate = (won / (won + lost) * 100) if (won + lost) > 0 else 0.0
    profit_sign = "+" if profit >= 0 else ""
    total_sign = "+" if total_profit >= 0 else ""
    profit_emoji = "\U0001f4b0" if profit > 0 else "\U0001f4c9" if profit < 0 else "➖"
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    lines = [
        f"\U0001f4ca *RESUMEN DIARIO \\- {today}*",
        "",
        f"✅ *Ganados:* {won}",
        f"❌ *Perdidos:* {lost}",
    ]
    if void > 0:
        lines.append(f"⬜ *Void:* {void}")
    lines.extend([
        f"\U0001f4c8 *Winrate:* {winrate:.1f}%",
        f"{profit_emoji} *Profit hoy:* {profit_sign}{profit:.2f}u",
        f"\U0001f4b9 *Profit total:* {total_sign}{total_profit:.2f}u",
        "",
        "\\#SmartOddsBasket \\#Resumen",
    ])
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _calc_stake(pick: Pick) -> float:
    try:
        prob = pick.estimated_probability or 0
        odds = pick.best_odds or 0
        if prob <= 0 or odds <= 1:
            return 0.0
        bankroll = settings.DEFAULT_BANKROLL
        b = odds - 1
        q = 1 - prob
        kelly = (b * prob - q) / b
        if kelly <= 0:
            return 0.0
        stake = bankroll * kelly * settings.KELLY_FRACTION
        max_stake = bankroll * settings.KELLY_MAX_STAKE_PCT
        return round(min(stake, max_stake), 2)
    except Exception:
        return 0.0


def _send_telegram(text: str, chat_id: str = None) -> bool:
    """Envia mensaje por Telegram (sincrono, fire-and-forget)."""
    try:
        token = settings.TELEGRAM_BOT_TOKEN
        target = chat_id or settings.TELEGRAM_CHAT_ID
        if not token or not target:
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json={
                "chat_id": target, "text": text, "parse_mode": "MarkdownV2",
            })
            if not resp.is_success or not resp.json().get("ok"):
                # Reintento sin formato si MarkdownV2 falla
                resp = client.post(url, json={
                    "chat_id": target,
                    "text": text.replace("*", "").replace("\\", ""),
                })
            return resp.is_success
    except Exception as e:
        logger.error(f"Error enviando Telegram: {e}")
        return False
