"""Exporta los datos estáticos (JSON) que consume la web.

Todo se calcula con la misma regla anti-fuga del resto del proyecto: el estado
"a hoy" usa solo partidos ya jugados, y las predicciones históricas son fuera de
muestra (modelo reentrenado al inicio de cada temporada con las anteriores).

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

from src.analysis.home_advantage import home_advantage
from src.config import PREMIER_LEAGUE, TEST_SEASONS, season_label, season_start_year
from src.data.fixtures import FIXTURES_URL, fetch_fixtures
from src.data.teams import display_name, slug
from src.features.build import FEATURES_PATH
from src.metrics import OUTCOMES, reliability_table, summarize
from src.models.experiments import predict_feature_model, prepare
from src.models.feature_models import PoissonGLMModel
from src.odds import shin_probabilities
from src.serving.predictor import EloPoissonPredictor
from src.serving.production import ALPHA, FEATURES
from src.serving.store import MatchStore

logger = logging.getLogger(__name__)

FIRST_REVIEW_SEASON = 2005   # después del burn-in del Elo y con 3 temporadas de entrenamiento
GRID = 7


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_default), encoding="utf-8")


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


def export_state(out: Path, store: MatchStore, today: pd.Timestamp) -> list[str]:
    """Estado actual de los equipos de la Premier de la temporada en curso + head-to-head de todos los pares."""
    season = season_start_year(today.date())
    teams = store.teams(PREMIER_LEAGUE, season) or store.teams(PREMIER_LEAGUE, season - 1)
    table = store.standings(PREMIER_LEAGUE, season, today).set_index("team")
    state = []
    for team in teams:
        state.append({
            "team": team, "name": display_name(team), "slug": slug(team),
            "elo": round(store.elo_as_of(team, today), 1),
            "form": store.recent_form(team, today),
            "rest": store.rest(team, today),
            "table": table.loc[team].to_dict() if team in table.index else None,
        })
    pairs = {f"{h}|{a}": store.head_to_head(h, a, today, n=6) for h in teams for a in teams if h != a}
    write(out / "state.json", {"as_of": today.date(), "season": season_label(season), "teams": state,
                               "standings": store.standings(PREMIER_LEAGUE, season, today).to_dict("records")})
    write(out / "h2h.json", pairs)
    return teams


def export_teams(out: Path, store: MatchStore) -> None:
    """Ficha por equipo: evolución del Elo y rendimiento por temporada frente a la media de la liga."""
    pl = store.matches[(store.matches.division == PREMIER_LEAGUE) & store.matches.home_goals.notna()]
    league = pl.groupby("season_start").apply(
        lambda g: pd.Series({"goals_per_team_game": (g.home_goals.sum() + g.away_goals.sum()) / (2 * len(g))}))
    index = []
    for team in store.teams(PREMIER_LEAGUE):
        seasons = []
        for s, g in pl[(pl.home_team == team) | (pl.away_team == team)].groupby("season_start"):
            home = g.home_team == team
            gf = np.where(home, g.home_goals, g.away_goals)
            ga = np.where(home, g.away_goals, g.home_goals)
            avg = float(league.loc[s, "goals_per_team_game"])
            standings = store.standings(PREMIER_LEAGUE, int(s), pd.Timestamp("2100-01-01")).set_index("team")
            seasons.append({
                "season": season_label(int(s)), "played": int(len(g)),
                "points": int(standings.loc[team, "points"]), "position": int(standings.loc[team, "position"]),
                "goals_for_per_game": r4(gf.mean()), "goals_against_per_game": r4(ga.mean()),
                "league_goals_per_team_game": r4(avg),
                "attack_vs_league_pct": r4(gf.mean() / avg - 1), "defence_vs_league_pct": r4(ga.mean() / avg - 1),
            })
        history = [{"date": m.date.date(), "elo": round(m.elo_after, 1), "division": m.division,
                    "opponent": m.opponent, "home": m.is_home, "score": f"{int(m.gf)}-{int(m.ga)}"}
                   for m in store.by_team[team] if m.played]
        write(out / "teams" / f"{slug(team)}.json",
              {"team": team, "name": display_name(team), "slug": slug(team), "seasons": seasons, "elo": history})
        index.append({"team": team, "name": display_name(team), "slug": slug(team),
                      "premier_seasons": len(seasons), "last_premier_season": seasons[-1]["season"]})
    write(out / "teams.json", sorted(index, key=lambda t: t["name"]))


def export_fixtures(out: Path, store: MatchStore, predictor: EloPoissonPredictor, today: pd.Timestamp) -> int:
    try:
        fixtures = fetch_fixtures()
    except requests.RequestException as err:  # la web sigue funcionando sin la lista de próximos partidos
        logger.warning("No se pudieron descargar los próximos partidos: %s", err)
        fixtures = pd.DataFrame()
    items = []
    for f in fixtures.itertuples(index=False):
        home, away, day = f.HomeTeam, f.AwayTeam, pd.Timestamp(f.date)
        try:
            elo_h, elo_a = store.elo_as_of(home, day), store.elo_as_of(away, day)
        except KeyError:
            logger.warning("Equipo desconocido en fixtures: %s / %s", home, away)
            continue
        items.append({
            "date": day.date(), "time": getattr(f, "Time", None), "home_team": home, "away_team": away,
            "home_name": display_name(home), "away_name": display_name(away),
            **prediction_payload(predictor, elo_h, elo_a),
            "market": market_probs([getattr(f, "B365H", np.nan), getattr(f, "B365D", np.nan), getattr(f, "B365A", np.nan)]),
            "context": {"form_home": store.recent_form(home, day), "form_away": store.recent_form(away, day),
                        "rest_home": store.rest(home, day), "rest_away": store.rest(away, day),
                        "head_to_head": store.head_to_head(home, away, day, n=6)},
        })
    write(out / "fixtures.json", {"generated_for": today.date(), "source": FIXTURES_URL, "matches": items})
    return len(items)


def export_review(out: Path, features: pd.DataFrame, current_season: int) -> dict:
    """Predicciones fuera de muestra de cada partido desde 2005-06 (reentrenamiento anual)."""
    seasons = list(range(FIRST_REVIEW_SEASON, current_season + 1))
    make = lambda: PoissonGLMModel(FEATURES, alpha=ALPHA)  # noqa: E731 - misma config que producción
    preds = predict_feature_model(make, features, seasons)
    df = features.merge(preds, on="match_id")
    odds = df[["b365_home", "b365_draw", "b365_away"]].to_numpy(float)
    ok = ~np.isnan(odds).any(axis=1)
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
                "home_name": display_name(r.home_team), "away_name": display_name(r.away_team),
                "score": [int(r.home_goals), int(r.away_goals)], "result": r.result,
                "elo": [round(r.elo_home, 1), round(r.elo_away, 1)],
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
    write(out / "calibration.json", {"seasons": "2023-24 a 2025-26", "matches": int(len(test)), **calib})
    return {"seasons": len(summary)}


def export_meta(out: Path, store: MatchStore, predictor: EloPoissonPredictor, today: pd.Timestamp, n_fixtures: int) -> None:
    played = store.matches[store.matches.home_goals.notna()]
    write(out / "meta.json", {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "as_of": today.date(),
        "last_match_in_data": played.date.max().date(),
        "fixtures_published": n_fixtures,
        "model": predictor.meta,
        "sources": [
            {"name": "Football-Data.co.uk", "url": "https://www.football-data.co.uk/",
             "use": "Resultados, estadísticas y cuotas de Premier League y Championship"},
            {"name": "ClubElo (vía Club Football Match Data, A. Gábor)",
             "url": "https://github.com/xgabora/Club-Football-Match-Data",
             "use": "Solo para comparar contra el Elo propio (no se usa para predecir)"},
        ],
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("web/public/data"))
    parser.add_argument("--today", type=str, default=None, help="Fecha de referencia (AAAA-MM-DD); por defecto, hoy")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    today = pd.Timestamp(args.today or date.today())
    out = args.out
    store, predictor = MatchStore.load(), EloPoissonPredictor.load()
    features = prepare(pd.read_parquet(FEATURES_PATH))

    export_model(out, predictor)
    teams = export_state(out, store, today)
    export_teams(out, store)
    n_fixtures = export_fixtures(out, store, predictor, today)
    review = export_review(out, features, season_start_year(today.date()))
    pl = store.matches[(store.matches.division == PREMIER_LEAGUE) & store.matches.home_goals.notna()]
    write(out / "home_advantage.json", home_advantage(pl))
    export_meta(out, store, predictor, today, n_fixtures)
    logger.info("Exportado en %s: %d equipos actuales, %d próximos partidos, %d temporadas de revisión",
                out, len(teams), n_fixtures, review["seasons"])


if __name__ == "__main__":
    main()
