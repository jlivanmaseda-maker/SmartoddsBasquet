"""Schema GraphQL (Strawberry) para SmartOdds Basketball.

Queries principales (consumidas por el frontend):
  - activePicks / resolvedPicks  — picks del sistema
  - stats                        — tracking agregado (profit, ROI, winrate)
  - standings(league)            — clasificacion por ELO de equipo
  - systemConfig                 — config publica (ligas, mercados, intervalos)

main.py monta este schema en /graphql automaticamente (try/except ImportError).
"""
from typing import List, Optional
from datetime import datetime

import strawberry

from app.config import settings
from app.db.database import SessionLocal
from app.models.match import Match
from app.models.team import Team
from app.models.bet import Pick


# ──────────────────────────────────────────────────────────────
# Tipos
# ──────────────────────────────────────────────────────────────

@strawberry.type
class MatchType:
    id: int
    league: Optional[str]
    league_tier: Optional[str]
    home_team: str
    away_team: str
    commence_time: Optional[datetime]
    is_completed: bool
    score: Optional[str]
    prob_home: Optional[float]
    prob_away: Optional[float]


@strawberry.type
class PickType:
    id: int
    bet_type: str
    best_odds: Optional[float]
    best_bookmaker: Optional[str]
    edge: Optional[float]
    estimated_probability: Optional[float]
    is_active: bool
    is_shadow: bool
    shadow_reasons: Optional[str]
    result: Optional[str]
    profit_units: Optional[float]
    clv_pct: Optional[float]
    created_at: Optional[datetime]
    match: Optional[MatchType]


@strawberry.type
class TeamType:
    id: int
    name: str
    league: Optional[str]
    elo_overall: Optional[float]
    wins: Optional[int]
    losses: Optional[int]


@strawberry.type
class StatsType:
    total_picks: int
    resolved: int
    won: int
    lost: int
    void: int
    profit_units: float
    roi_pct: float
    winrate_pct: float
    active_picks: int
    shadow_picks: int


# ──────────────────────────────────────────────────────────────
# Helpers de mapeo
# ──────────────────────────────────────────────────────────────

def _match_to_type(m: Match) -> Optional[MatchType]:
    if not m:
        return None
    return MatchType(
        id=m.id, league=m.league, league_tier=m.league_tier,
        home_team=m.home_team, away_team=m.away_team,
        commence_time=m.commence_time, is_completed=bool(m.is_completed),
        score=m.score, prob_home=m.prob_home, prob_away=m.prob_away,
    )


def _pick_to_type(p: Pick, m: Match) -> PickType:
    return PickType(
        id=p.id, bet_type=p.bet_type, best_odds=p.best_odds,
        best_bookmaker=p.best_bookmaker, edge=p.edge,
        estimated_probability=p.estimated_probability,
        is_active=bool(p.is_active), is_shadow=bool(p.is_shadow),
        shadow_reasons=p.shadow_reasons, result=p.result,
        profit_units=p.profit_units, clv_pct=p.clv_pct,
        created_at=p.created_at, match=_match_to_type(m),
    )


# ──────────────────────────────────────────────────────────────
# Query
# ──────────────────────────────────────────────────────────────

@strawberry.type
class Query:

    @strawberry.field
    def active_picks(self, include_shadow: bool = False, limit: int = 50) -> List[PickType]:
        db = SessionLocal()
        try:
            q = db.query(Pick).filter(
                Pick.is_active == True,            # noqa: E712
                Pick.result.is_(None),
            )
            if not include_shadow:
                q = q.filter(Pick.is_shadow == False)  # noqa: E712
            picks = q.order_by(Pick.created_at.desc()).limit(limit).all()
            out = []
            for p in picks:
                m = db.query(Match).filter(Match.id == p.match_id).first()
                out.append(_pick_to_type(p, m))
            return out
        finally:
            db.close()

    @strawberry.field
    def resolved_picks(self, include_shadow: bool = True, limit: int = 100) -> List[PickType]:
        db = SessionLocal()
        try:
            q = db.query(Pick).filter(Pick.result.in_(["won", "lost", "void"]))
            if not include_shadow:
                q = q.filter(Pick.is_shadow == False)  # noqa: E712
            picks = q.order_by(Pick.resolved_at.desc()).limit(limit).all()
            out = []
            for p in picks:
                m = db.query(Match).filter(Match.id == p.match_id).first()
                out.append(_pick_to_type(p, m))
            return out
        finally:
            db.close()

    @strawberry.field
    def stats(self, include_shadow: bool = False) -> StatsType:
        db = SessionLocal()
        try:
            q = db.query(Pick)
            if not include_shadow:
                q = q.filter(Pick.is_shadow == False)  # noqa: E712
            picks = q.all()
            resolved = [p for p in picks if p.result in ("won", "lost", "void")]
            won = sum(1 for p in resolved if p.result == "won")
            lost = sum(1 for p in resolved if p.result == "lost")
            void = sum(1 for p in resolved if p.result == "void")
            settled = won + lost
            profit = sum(p.profit_units or 0.0 for p in resolved)
            staked = sum(1 for p in resolved if p.result in ("won", "lost"))
            return StatsType(
                total_picks=len(picks),
                resolved=len(resolved),
                won=won, lost=lost, void=void,
                profit_units=round(profit, 2),
                roi_pct=round(profit / staked * 100, 2) if staked else 0.0,
                winrate_pct=round(won / settled * 100, 2) if settled else 0.0,
                active_picks=sum(1 for p in picks if not p.is_shadow),
                shadow_picks=sum(1 for p in picks if p.is_shadow),
            )
        finally:
            db.close()

    @strawberry.field
    def standings(self, league: Optional[str] = None, limit: int = 50) -> List[TeamType]:
        db = SessionLocal()
        try:
            q = db.query(Team)
            if league:
                q = q.filter(Team.league == league)
            teams = q.order_by(Team.elo_overall.desc()).limit(limit).all()
            return [
                TeamType(id=t.id, name=t.name, league=t.league,
                         elo_overall=t.elo_overall, wins=t.wins, losses=t.losses)
                for t in teams
            ]
        finally:
            db.close()

    @strawberry.field
    def system_config(self) -> strawberry.scalars.JSON:
        return {
            "sport": settings.SPORT,
            "monitored_leagues": settings.MONITORED_LEAGUES,
            "active_markets": settings.ACTIVE_MARKETS,
            "system_min_edge": settings.SYSTEM_MIN_EDGE,
        }


schema = strawberry.Schema(query=Query)
