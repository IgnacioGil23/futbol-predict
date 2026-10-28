"""Exporta los datos estáticos (JSON) que consume la web.

Todo se calcula con la misma regla anti-fuga del resto del proyecto: el estado
"a hoy" usa solo partidos ya jugados, y las predicciones históricas son fuera de
muestra (modelo reentrenado al inicio de cada temporada con las anteriores).

Cada liga se exporta con su contexto (src/export/league_context.py): la Premier en la raíz de `--out` y las demás
en `--out`/leagues/<liga>/; leagues.json lista las ligas publicadas.

Uso:
    python -m src.export.site --out web/public/data
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson

from src.config import TEST_SEASONS, season_label, season_start_year
from src.data.fixtures import FIXTURES_URL
from src.data.leagues import LEAGUES
from src.data.schedule import check_against_results
from src.data.teams import slug
from src.export.league_context import LeagueContext, league_context, leagues_index, premier_context
from src.export.season import build_season, current_state
from src.export.stats import build_stats, remaining_difficulty
from src.metrics import OUTCOMES, reliability_table, summarize
from src.models.experiments import predict_feature_model
from src.models.feature_models import PoissonGLMModel
from src.odds import shin_probabilities
from src.serving.predictor import EloPoissonPredictor
from src.serving.production import ALPHA, FEATURES

logger = logging.getLogger(__name__)

GRID = 7
# Columnas de la tabla de variables con el rating de cada tipo.
RATING_COLUMNS = {"elo": ("elo_home", "elo_away"), "odds_elo": ("odds_elo_home", "odds_elo_away")}


def _without_nan(o):
    """NaN -> None en todo el payload: json no pasa los float (ni np.float64, que hereda de float) por `default`, y
    escribiría NaN, que no es JSON válido."""
    if isinstance(o, float) and o != o:
        return None
    if isinstance(o, dict):
        return {k: _without_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_without_nan(v) for v in o]
    return o


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_without_nan(payload), ensure_ascii=False, separators=(",", ":"), default=_default,
                               allow_nan=False), encoding="utf-8")


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else round(float(o), 6)
    if isinstance(o, (pd.Timestamp, date)):
        return o.isoformat()[:10]
    raise TypeError(type(o))


def r4(x) -> float:
    return round(float(x), 4)


def prediction_payload(predictor: EloPoissonPredictor, elo_home: float, elo_away: float) -> dict:
    p = predictor.predict(elo_home, elo_away)
    return {
        "elo": {"home": round(elo_home, 1), "away": round(elo_away, 1)},
        "expected_goals": {"home": r4(p.lam), "away": r4(p.mu)},
        "probabilities": {"home": r4(p.probs[0]), "draw": r4(p.probs[1]), "away": r4(p.probs[2])},
        "score_grid": [[r4(v) for v in row] for row in p.matrix[:GRID, :GRID]],
        "top_scores": [{**s, "probability": r4(s["probability"])} for s in p.top_scores(6)],
    }


def top_score_probability(lam, mu) -> np.ndarray:
    """Probabilidad del marcador más probable con goles Poisson independientes.

    La grilla es el producto de dos Poisson, así que su máximo es el producto de las dos modas (floor de cada tasa).
    """
    lam, mu = np.asarray(lam, dtype=float), np.asarray(mu, dtype=float)
    return poisson.pmf(np.floor(lam), lam) * poisson.pmf(np.floor(mu), mu)


def market_probs(odds_row) -> dict | None:
    odds = np.asarray(odds_row, dtype=float)
    if np.isnan(odds).any() or (odds <= 1).any():
        return None
    p = shin_probabilities(odds[None, :])[0]
    return {"home": r4(p[0]), "draw": r4(p[1]), "away": r4(p[2])}


# ---------------------------------------------------------------------- partes

def export_model(out: Path, predictor: EloPoissonPredictor) -> None:
    """Parámetros del modelo + vectores de prueba para verificar la implementación en TypeScript."""
    vectors = []
    for diff in (-400, -150, -30, 0, 45, 120, 300):
        pred = predictor.predict(1800 + diff / 2, 1800 - diff / 2)
        vectors.append({"elo_diff": diff, "lam": pred.lam, "mu": pred.mu,
                        "probabilities": pred.probs.tolist(), "score_0_0": float(pred.matrix[0, 0]),
                        "score_2_1": float(pred.matrix[2, 1])})
    write(out / "model.json", {"params": predictor.params, "max_goals": 10, "test_vectors": vectors,
                               "meta": predictor.meta})


def export_state(out: Path, ctx: LeagueContext, today: pd.Timestamp) -> list[str]:
    """Estado actual de los equipos de la primera división en la temporada en curso + head-to-head de todos los pares.
    "elo" es el rating que usa el modelo publicado."""
    store, top, rating = ctx.store, ctx.top, ctx.predictor.rating
    season = season_start_year(today.date())
    teams = store.teams(top, season) or store.teams(top, season - 1)
    table = store.standings(top, season, today).set_index("team")
    state = []
    for team in teams:
        state.append({
            "team": team, "name": ctx.name_of(team), "slug": slug(team),
            "elo": round(store.rating_as_of(team, today, rating), 1),
            "form": store.recent_form(team, today),
            "rest": store.rest(team, today),
            "table": table.loc[team].to_dict() if team in table.index else None,
        })
    pairs = {f"{h}|{a}": store.head_to_head(h, a, today, n=6) for h in teams for a in teams if h != a}
    write(out / "state.json", {"as_of": today.date(), "season": season_label(season), "teams": state,
                               "standings": store.standings(top, season, today).to_dict("records")})
    write(out / "h2h.json", pairs)
    return teams


def export_teams(out: Path, ctx: LeagueContext) -> None:
    """Ficha por equipo: evolución del rating del modelo y rendimiento por temporada frente a la media de la liga."""
    store, top, rating = ctx.store, ctx.top, ctx.predictor.rating
    pl = store.matches[(store.matches.division == top) & store.matches.home_goals.notna()]
    league = pl.groupby("season_start").apply(
        lambda g: pd.Series({"goals_per_team_game": (g.home_goals.sum() + g.away_goals.sum()) / (2 * len(g))}))
    finals = {int(s): store.standings(top, int(s), pd.Timestamp("2100-01-01")).set_index("team")
              for s in pl.season_start.unique()}
    index = []
    for team in store.teams(top):
        seasons = []
        for s, g in pl[(pl.home_team == team) | (pl.away_team == team)].groupby("season_start"):
            home = g.home_team == team
            gf = np.where(home, g.home_goals, g.away_goals)
            ga = np.where(home, g.away_goals, g.home_goals)
            avg = float(league.loc[s, "goals_per_team_game"])
            standings = finals[int(s)]
            seasons.append({
                "season": season_label(int(s)), "played": int(len(g)),
                "points": int(standings.loc[team, "points"]), "position": int(standings.loc[team, "position"]),
                "goals_for_per_game": r4(gf.mean()), "goals_against_per_game": r4(ga.mean()),
                "league_goals_per_team_game": r4(avg),
                "attack_vs_league_pct": r4(gf.mean() / avg - 1), "defence_vs_league_pct": r4(ga.mean() / avg - 1),
            })
        history = [{"date": m.date.date(), "elo": round(m.rating(rating, "after"), 1), "division": m.division,
                    "opponent": m.opponent, "home": m.is_home, "score": f"{int(m.gf)}-{int(m.ga)}"}
                   for m in store.by_team[team] if m.played]
        ident = {"team": team, "name": ctx.name_of(team), "slug": slug(team), **ctx.badge_of(team),
                 **ctx.stadium_of(team)}
        write(out / "teams" / f"{slug(team)}.json", {**ident, "seasons": seasons, "elo": history})
        index.append({**ident, "top_seasons": len(seasons), "last_top_season": seasons[-1]["season"]})
    write(out / "teams.json", sorted(index, key=lambda t: t["name"]))


def export_upcoming(out: Path, ctx: LeagueContext, today: pd.Timestamp, n_matchdays: int = 3) -> dict:
    """Próximas jornadas (calendario de openfootball) con la predicción y el contexto de cada partido.

    Las cuotas de Bet365 se agregan cuando Football-Data ya publicó el partido en
    fixtures.csv (pocos días antes). Los horarios van en hora de Argentina.
    """
    store, predictor, top = ctx.store, ctx.predictor, ctx.top
    season = season_start_year(today.date())
    quality: dict = {}
    try:
        schedule = ctx.schedule(season)
    except requests.RequestException as err:  # la web sigue funcionando sin el calendario
        logger.warning("%s: no se pudo descargar el calendario: %s", ctx.code, err)
        schedule = pd.DataFrame(columns=["matchday", "date", "time_uk", "kickoff_ar", "home_team", "away_team", "played"])
        quality["schedule_error"] = str(err)
    try:
        fixtures = ctx.fixtures()
    except requests.RequestException as err:
        logger.warning("No se pudieron descargar las cuotas de los próximos partidos: %s", err)
        fixtures = pd.DataFrame(columns=["HomeTeam", "AwayTeam", "B365H", "B365D", "B365A"])
    odds = {(f.HomeTeam, f.AwayTeam): [f.B365H, f.B365D, f.B365A] for f in fixtures.itertuples(index=False)}

    results = store.matches[(store.matches.division == top) & (store.matches.season_start == season)
                            & store.matches.home_goals.notna()]
    if len(schedule):
        quality.update(check_against_results(schedule, results))
        if quality["not_found_in_football_data"] or quality["score_mismatches"]:
            logger.warning("%s: el calendario y Football-Data no coinciden: %s", ctx.code, quality)
    already_played = set(zip(results.home_team, results.away_team))
    pending = schedule[~schedule["played"].astype(bool) & (schedule["date"] >= today.normalize())]
    pending = pending[[(h, a) not in already_played for h, a in zip(pending.home_team, pending.away_team)]]
    known = set(store.by_team)                 # con historia (antes de la fecha 1 nadie jugó todavía esta temporada)
    order = pending.groupby("matchday")["date"].min().sort_values().index[:n_matchdays]

    matchdays = []
    for md in order:
        games = pending[pending.matchday == md].sort_values(["date", "time_uk", "home_team"], na_position="last")
        items = []
        for g in games.itertuples(index=False):
            if g.home_team not in known or g.away_team not in known:
                logger.warning("%s: equipo del calendario sin datos: %s vs %s", ctx.code, g.home_team, g.away_team)
                continue
            day = pd.Timestamp(g.date)
            elo_h = store.rating_as_of(g.home_team, day, predictor.rating)
            elo_a = store.rating_as_of(g.away_team, day, predictor.rating)
            items.append({
                "date": day.date(), "kickoff_ar": g.kickoff_ar,
                "home_team": g.home_team, "away_team": g.away_team,
                "home_name": ctx.name_of(g.home_team), "away_name": ctx.name_of(g.away_team),
                "home_slug": slug(g.home_team), "away_slug": slug(g.away_team),
                **prediction_payload(predictor, elo_h, elo_a),
                "market": market_probs(odds[(g.home_team, g.away_team)]) if (g.home_team, g.away_team) in odds else None,
                "context": {"form_home": store.recent_form(g.home_team, day), "form_away": store.recent_form(g.away_team, day),
                            "rest_home": store.rest(g.home_team, day), "rest_away": store.rest(g.away_team, day),
                            "head_to_head": store.head_to_head(g.home_team, g.away_team, day, n=6)},
            })
        if items:
            matchdays.append({"matchday": int(md), "from": items[0]["date"], "to": items[-1]["date"], "matches": items})

    payload = {
        "generated_for": today.date(), "season": season_label(season), "model_version": predictor.version,
        "timezone": "America/Argentina/Buenos_Aires",
        "sources": {"schedule": ctx.schedule_url(season), "odds": FIXTURES_URL},
        "quality": quality, "matchdays": matchdays,
    }
    write(out / "upcoming.json", payload)
    return {"matchdays": len(matchdays), "matches": sum(len(m["matches"]) for m in matchdays)}


def export_stats(out: Path, ctx: LeagueContext, today: pd.Timestamp) -> list[str]:
    """Sección Estadísticas: temporada en curso y la anterior completa (stats/<temporada>.json + stats/index.json).

    La dificultad del calendario usa el mismo rating que el resto del sitio. Si el calendario o los fixtures no se
    pueden descargar, esas partes quedan en null y el resto se exporta igual.
    """
    matches = ctx.matches
    played = matches[matches.home_goals.notna()]
    current = season_start_year(today.date())
    in_progress = bool(((played.division == ctx.top) & (played.season_start == current)).any())
    if not in_progress:
        current -= 1                     # receso: se muestra la temporada que terminó (sin calendario restante)
    difficulty = referees_next = None
    if in_progress:
        difficulty, referees_next = _upcoming_context(ctx, current, today)

    index = []
    for season in (current, current - 1):
        is_current = in_progress and season == current
        payload = build_stats(played, season, difficulty if is_current else None, referees_next if is_current else None,
                              division=ctx.top)
        write(out / "stats" / f"{payload['season']}.json", payload)
        index.append({"season": payload["season"], "current": is_current})
    write(out / "stats" / "index.json", index)
    return [i["season"] for i in index]


def _upcoming_context(ctx: LeagueContext, season: int, today: pd.Timestamp) -> tuple[dict | None, dict | None]:
    """Dificultad del calendario restante y árbitros designados; None en lo que no se pueda descargar."""
    difficulty = referees_next = None
    store = ctx.store
    try:
        state = current_state(store, ctx.schedule(season), today, division=ctx.top)
        if state.fixtures:
            rating = ctx.predictor.rating
            ratings = {t: store.rating_as_of(t, today, rating) if t in store.by_team else None for t in state.teams}
            if None in ratings.values():
                logger.warning("%s: estadísticas sin dificultad del calendario: equipos sin rating %s", ctx.code,
                               [t for t, r in ratings.items() if r is None])
            else:
                difficulty = remaining_difficulty(state.fixtures, ratings)
    except requests.RequestException as err:
        logger.warning("%s: estadísticas sin dificultad del calendario: %s", ctx.code, err)
    try:
        fixtures = ctx.fixtures()
        if "Referee" in fixtures.columns:
            refs = {f"{f.HomeTeam}|{f.AwayTeam}": str(f.Referee).strip() for f in fixtures.itertuples(index=False)
                    if isinstance(f.Referee, str) and f.Referee.strip()}
            referees_next = refs or None
    except requests.RequestException as err:
        logger.warning("%s: estadísticas sin árbitros de la próxima fecha: %s", ctx.code, err)
    return difficulty, referees_next


def export_review(out: Path, ctx: LeagueContext, current_season: int) -> dict:
    """Predicciones fuera de muestra de cada partido (reentrenamiento anual), desde la temporada siguiente a la primera
    de entrenamiento de la liga."""
    features, rating = ctx.features, ctx.predictor.rating
    seasons = list(range(ctx.first_train + 1, current_season + 1))
    make = lambda: PoissonGLMModel(FEATURES, alpha=ALPHA)  # noqa: E731 - misma config que producción
    preds = predict_feature_model(make, features, seasons, first_train=ctx.first_train)
    rating_home, rating_away = RATING_COLUMNS[rating]
    df = features.merge(preds, on="match_id")
    odds = df[["b365_home", "b365_draw", "b365_away"]].to_numpy(float)
    ok = ~np.isnan(odds).any(axis=1) & (odds > 1).all(axis=1)
    market = np.full((len(df), 3), np.nan)
    market[ok] = shin_probabilities(odds[ok])
    df[["m_home", "m_draw", "m_away"]] = market
    summary = []
    for season, g in df.groupby("season"):
        model_p = g[["p_home", "p_draw", "p_away"]].to_numpy()
        res = g["result"].to_numpy()
        both = ~np.isnan(g[["m_home", "m_draw", "m_away"]].to_numpy()).any(axis=1)
        s_model = summarize(model_p[both], res[both])
        s_market = summarize(g[["m_home", "m_draw", "m_away"]].to_numpy()[both], res[both])
        summary.append({"season": season, "matches": int(len(g)), "compared_matches": int(both.sum()),
                        "model": {k: r4(s_model[k]) for k in ("log_loss", "rps", "accuracy")},
                        "market": {k: r4(s_market[k]) for k in ("log_loss", "rps", "accuracy")}})
        matches = []
        for r in g.itertuples(index=False):
            k = OUTCOMES.index(r.result)
            matches.append({
                "id": r.match_id, "date": r.date, "home_team": r.home_team, "away_team": r.away_team,
                "home_name": ctx.name_of(r.home_team), "away_name": ctx.name_of(r.away_team),
                "score": [int(r.home_goals), int(r.away_goals)], "result": r.result,
                "elo": [round(getattr(r, rating_home), 1), round(getattr(r, rating_away), 1)],
                "expected_goals": [r4(r.lam), r4(r.mu)],
                "p": [r4(r.p_home), r4(r.p_draw), r4(r.p_away)],
                "market": None if np.isnan(r.m_home) else [r4(r.m_home), r4(r.m_draw), r4(r.m_away)],
                "p_actual": r4([r.p_home, r.p_draw, r.p_away][k]),
            })
        write(out / "review" / f"{season}.json", {"season": season, "matches": matches})
    write(out / "review" / "index.json", summary)

    test = df[df.season_start.isin(TEST_SEASONS) & ok]
    calib = {}
    for name, cols in (("model", ["p_home", "p_draw", "p_away"]), ("market", ["m_home", "m_draw", "m_away"])):
        t = reliability_table(test[cols].to_numpy(), test["result"].to_numpy(), n_bins=8)
        calib[name] = t[t.n >= 25].round(4).to_dict("records")
    write(out / "calibration.json", {"seasons": f"{season_label(min(TEST_SEASONS))} a {season_label(max(TEST_SEASONS))}",
                                     "matches": int(len(test)), **calib})
    top = top_score_probability(df["lam"], df["mu"])
    return {"seasons": len(summary), "matches": int(len(df)), "first_season": seasons[0], "last_season": current_season,
            "max_top_score": r4(top.max())}


def export_meta(out: Path, ctx: LeagueContext, today: pd.Timestamp, n_upcoming: int, review: dict) -> None:
    played = ctx.store.matches[ctx.store.matches.home_goals.notna()]
    lg = ctx.league
    repo = lg["schedule_url"].split("/master/")[0].replace("raw.githubusercontent.com", "github.com")
    sources = [
        {"name": "Football-Data.co.uk", "url": "https://www.football-data.co.uk/",
         "use": f"Resultados, estadísticas y cuotas de {lg['competition']} y {lg['second_name']}"},
        {"name": f"{repo.split('github.com/')[1]} (dominio público)", "url": repo,
         "use": "Calendario de las próximas jornadas (días y horarios)"},
    ]
    if ctx.is_premier:
        sources.append({"name": "ClubElo (vía Club Football Match Data, A. Gábor)",
                        "url": "https://github.com/xgabora/Club-Football-Match-Data",
                        "use": "Solo para comparar contra el Elo propio (no se usa para predecir)"})
    write(out / "meta.json", {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "as_of": today.date(),
        "league": {"code": ctx.code, "competition": lg["competition"], "country": lg["name"],
                   "second": lg["second_name"]},
        "last_match_in_data": played.date.max().date(),
        "upcoming_matches": n_upcoming,
        # Resumen de las predicciones fuera de muestra (sección Revisión), para los textos de la web.
        "review": {"matches": review["matches"], "first_season": season_label(review["first_season"]),
                   "last_season": season_label(review["last_season"]), "max_top_score": review["max_top_score"]},
        "model_version": ctx.predictor.version,
        "model": ctx.predictor.meta,
        "sources": sources,
    })


def export_league(out_root: Path, ctx: LeagueContext, today: pd.Timestamp) -> dict:
    """Todos los JSON de una liga en su carpeta."""
    out = ctx.out_dir(out_root)
    export_model(out, ctx.predictor)
    teams = export_state(out, ctx, today)
    export_teams(out, ctx)
    upcoming = export_upcoming(out, ctx, today)
    stats_seasons = export_stats(out, ctx, today)
    review = export_review(out, ctx, season_start_year(today.date()))
    # La simulación de la temporada usa el modelo de Elo de resultados (docs/preregistro_temporada.md y
    # docs/preregistro_ligas.md): actualiza el rating con los resultados simulados, algo que el rating basado en
    # cuotas no puede hacer.
    season_sim = build_season(ctx, today)
    if season_sim is not None:
        write(out / "season.json", season_sim)
    else:
        (out / "season.json").unlink(missing_ok=True)
    export_meta(out, ctx, today, upcoming["matches"], review)
    logger.info("%s -> %s: %d equipos actuales, %d próximos partidos en %d jornadas, %d temporadas de revisión, "
                "estadísticas de %s", ctx.code, out, len(teams), upcoming["matches"], upcoming["matchdays"],
                review["seasons"], ", ".join(stats_seasons))
    return {"teams": len(teams), **upcoming}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("web/public/data"))
    parser.add_argument("--today", type=str, default=None, help="Fecha de referencia (AAAA-MM-DD); por defecto, hoy")
    parser.add_argument("--leagues", nargs="*", default=["ENG", *LEAGUES], help="ligas a exportar (ENG = Premier)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    today = pd.Timestamp(args.today or date.today())
    contexts = []
    for code in args.leagues:
        if code == "ENG":                          # la Premier es el producto base: si falla, falla la exportación
            ctx = premier_context()
            export_league(args.out, ctx, today)
            contexts.append(ctx)
            continue
        try:                                       # otra liga que falle (sin datos, calendario roto) no frena al resto
            ctx = league_context(code)
            export_league(args.out, ctx, today)
        except Exception:
            logger.exception("%s: no se exporta", code)
            continue
        contexts.append(ctx)
    write(args.out / "leagues.json", leagues_index(contexts))


if __name__ == "__main__":
    main()
