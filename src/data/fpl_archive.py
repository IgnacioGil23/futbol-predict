"""Archivo histórico de Fantasy Premier League (datos por jugador y partido) y sus controles de calidad.

Fuente: https://github.com/vaastav/Fantasy-Premier-League, fijada a un commit para que la descarga sea
reproducible. El repositorio no declara licencia y los datos vienen de la API de Fantasy: como con
Football-Data, se descargan al construir y NO se versionan ni se republican; solo se publican
resultados agregados.

Se usa en la prueba histórica de los candidatos A (xG) y B (fuerza de la alineación), ver
docs/preregistro_fpl.md. Por jugador y partido: minutos, titular, precio en esa fecha del torneo
("value", en décimas de millón), xG y xG concedido.

Problemas conocidos del archivo, corregidos acá y controlados en `assert_quality`:
* 2022-23, fechas 1 a 15: titulares y xG vienen en 0 para todos los equipos. Es un dato FALTANTE
  (el archivo empezó a registrarlos en la fecha 16), no un cero real: se marca como NaN.
* 2024-25: Fantasy agregó entrenadores como elementos del juego (posición "AM", chip "Assistant
  Manager"), sin minutos. No son jugadores: se excluyen.
* 2025-26: filas repetidas idénticas (mismo jugador y partido): se deduplican.

Salidas:
    data/processed/fpl_player_matches.parquet   una fila por jugador y partido, vinculada al match_id
    data/processed/fpl_quality.json              controles de calidad

Uso:
    python -m src.data.fpl_archive                  # descarga (si falta), controla y guarda
    python -m src.data.fpl_archive --verify-live    # además contrasta precios con la API oficial
"""

import argparse
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PREMIER_LEAGUE, PROCESSED_DIR, RAW_DIR, season_label
from src.data.download import _fetch, _session

logger = logging.getLogger(__name__)

ARCHIVE_REPO = "vaastav/Fantasy-Premier-League"
ARCHIVE_COMMIT = "9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88"   # 28/08/2026
ARCHIVE_URL = "https://raw.githubusercontent.com/{repo}/{commit}/data/{season}/{file}"
ARCHIVE_FILES = {"gw": "gws/merged_gw.csv", "fixtures": "fixtures.csv", "teams": "teams.csv",
                 "players": "players_raw.csv"}
ARCHIVE_DIR = RAW_DIR / "fpl_archive" / ARCHIVE_COMMIT[:7]
FPL_SEASONS = [2022, 2023, 2024, 2025]
PLAYER_MATCHES_PATH = PROCESSED_DIR / "fpl_player_matches.parquet"
QUALITY_PATH = PROCESSED_DIR / "fpl_quality.json"
FPL_API = "https://fantasy.premierleague.com/api"

PLAYER_POSITIONS = {"GK", "DEF", "MID", "FWD"}
MANAGER_POSITION = "AM"
LINEUP_SIZE = 11
MIN_START_PRICE_AGREEMENT = 0.99   # share de jugadores cuyo primer precio coincide con el precio inicial

# Código de equipo de Fantasy (estable entre temporadas) -> nombre canónico de Football-Data.
FPL_TEAM_CODES: dict[int, str] = {
    1: "Man United", 2: "Leeds", 3: "Arsenal", 4: "Newcastle", 6: "Tottenham", 7: "Aston Villa",
    8: "Chelsea", 9: "Coventry", 11: "Everton", 13: "Leicester", 14: "Liverpool", 17: "Nott'm Forest",
    20: "Southampton", 21: "West Ham", 31: "Crystal Palace", 36: "Brighton", 39: "Wolves", 40: "Ipswich",
    43: "Man City", 49: "Sheffield United", 54: "Fulham", 56: "Sunderland", 88: "Hull", 90: "Burnley",
    91: "Bournemouth", 94: "Brentford", 102: "Luton",
}
LINEUP_COLUMNS = ["starts", "expected_goals", "expected_goals_conceded"]   # los que faltan antes de la fecha 16 de 2022-23
OUTPUT_COLUMNS = ["season_start", "match_id", "fixture", "gameweek", "kickoff", "team", "is_home", "element",
                  "player_code", "name", "position", "minutes", "starts", "price", "expected_goals",
                  "expected_goals_conceded"]


class ArchiveQualityError(RuntimeError):
    """El archivo no pasa un control de calidad que invalidaría las variables."""


# ------------------------------------------------------------------ descarga

def season_dir(start: int) -> Path:
    return ARCHIVE_DIR / season_label(start)


def download_archive(seasons: list[int] = FPL_SEASONS, force: bool = False) -> dict[str, str]:
    """Descarga los archivos que falten y devuelve el SHA-256 de cada uno (queda en el reporte)."""
    session, hashes = _session(), {}
    for start in seasons:
        for file in ARCHIVE_FILES.values():
            path = season_dir(start) / Path(file).name
            if force or not path.exists():
                url = ARCHIVE_URL.format(repo=ARCHIVE_REPO, commit=ARCHIVE_COMMIT, season=season_label(start), file=file)
                logger.info("Descargado %s (%d bytes)", url, _fetch(session, url, path))
            hashes[f"{season_label(start)}/{Path(file).name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def read_season(start: int) -> dict[str, pd.DataFrame]:
    d = season_dir(start)
    return {key: pd.read_csv(d / Path(file).name, low_memory=False) for key, file in ARCHIVE_FILES.items()}


# ------------------------------------------------------------------ limpieza

def map_teams(teams: pd.DataFrame) -> dict[int, str]:
    """id de equipo en la temporada -> nombre canónico (vía el código estable)."""
    unknown = sorted(set(teams["code"]) - set(FPL_TEAM_CODES))
    if unknown:
        raise ArchiveQualityError(f"Códigos de equipo sin mapear: {unknown}")
    return {int(i): FPL_TEAM_CODES[int(c)] for i, c in zip(teams["id"], teams["code"])}


def clean_player_rows(gw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Excluye entrenadores y filas repetidas idénticas. Un jugador repetido con datos distintos en el
    mismo partido no tiene una corrección obvia: es un error."""
    managers = gw["position"] == MANAGER_POSITION
    if (gw.loc[managers, ["minutes", "starts"]].to_numpy() != 0).any():
        raise ArchiveQualityError("Hay entrenadores (posición AM) con minutos o titularidades")
    gw = gw[~managers]
    exact = int(gw.duplicated().sum())
    gw = gw.drop_duplicates()
    conflicting = gw[gw.duplicated(["element", "fixture"], keep=False)]
    if len(conflicting):
        raise ArchiveQualityError(
            f"Jugadores repetidos con datos distintos: {conflicting[['name', 'fixture']].values.tolist()[:5]}")
    return gw, {"managers_removed": int(managers.sum()), "exact_duplicates_removed": exact}


def mask_missing_lineups(rows: pd.DataFrame) -> tuple[pd.DataFrame, list[int]]:
    """Marca como faltantes (NaN) titulares y xG de las fechas en que el archivo no los registró.

    Una fecha "sin registro" es una en la que TODOS los equipos-partido suman 0 titulares: con 11
    titulares obligatorios, un 0 no puede ser real. Solo se aceptan al principio de la temporada
    (un hueco en el medio sería otro problema y se reporta en los controles)."""
    starts = rows.groupby(["gameweek", "match_id", "team"])["starts"].sum()
    empty = starts.groupby("gameweek").apply(lambda s: bool((s == 0).all()))
    missing = sorted(int(g) for g in empty[empty].index)
    rows = rows.copy()
    rows.loc[rows["gameweek"].isin(missing), LINEUP_COLUMNS] = np.nan
    return rows, missing


# ------------------------------------------------------------------ vinculación

def link_fixtures(start: int, fixtures: pd.DataFrame, teams: pd.DataFrame,
                  matches: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Vincula cada partido de Fantasy con el de Football-Data (misma temporada, local y visitante)."""
    ids = map_teams(teams)
    fx = fixtures.assign(home_team=fixtures["team_h"].map(ids), away_team=fixtures["team_a"].map(ids),
                         kickoff=pd.to_datetime(fixtures["kickoff_time"], utc=True))
    ours = matches[(matches.division == PREMIER_LEAGUE) & (matches.season_start == start)]
    linked = fx.merge(ours[["match_id", "home_team", "away_team", "date", "home_goals", "away_goals"]],
                      on=["home_team", "away_team"], how="left", validate="one_to_one")
    ok = linked["match_id"].notna()
    same_score = (linked["team_h_score"] == linked["home_goals"]) & (linked["team_a_score"] == linked["away_goals"])
    day_gap = (linked["kickoff"].dt.tz_localize(None).dt.normalize() - linked["date"]).dt.days.abs()
    return linked[ok], {
        "fixtures": int(len(fx)), "finished": int(fx["finished"].astype(bool).sum()),
        "linked": int(ok.sum()), "unlinked": linked.loc[~ok, ["home_team", "away_team"]].values.tolist(),
        "score_matches": int(same_score[ok].sum()),
        "score_mismatches": linked.loc[ok & ~same_score, ["match_id", "home_team", "away_team"]].values.tolist(),
        "max_day_gap": int(day_gap[ok].max()) if ok.any() else None,
    }


def start_price_agreement(rows: pd.DataFrame, players: pd.DataFrame) -> dict:
    """El precio de cada jugador en su primera fecha tiene que ser su precio inicial de la temporada
    (players_raw: now_cost - cost_change_start). Si el archivo guardara un precio posterior (fuga), no
    coincidiría."""
    first = rows.sort_values(["gameweek", "kickoff"]).groupby("element")["price"].first()
    start_cost = (players["now_cost"] - players["cost_change_start"]).set_axis(players["id"])
    common = first.index.intersection(start_cost.index)
    agree = first[common] == start_cost[common]
    return {"players": int(len(common)), "agreement": float(agree.mean()),
            "examples_disagree": [[int(e), int(first[e]), int(start_cost[e])] for e in common[~agree.to_numpy()][:5]]}


def player_matches(start: int, raw: dict[str, pd.DataFrame], matches: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    gw, cleaning = clean_player_rows(raw["gw"])
    linked, link = link_fixtures(start, raw["fixtures"], raw["teams"], matches)
    names = dict(zip(raw["teams"]["name"], raw["teams"]["code"].map(FPL_TEAM_CODES)))
    rows = gw.merge(linked[["id", "match_id", "home_team", "away_team", "kickoff"]], left_on="fixture",
                    right_on="id", how="inner", validate="many_to_one")
    rows["is_home"] = rows["was_home"].astype(bool)
    archive_team = rows["team"].map(names)       # equipo del jugador según el archivo
    rows["team"] = np.where(rows["is_home"], rows["home_team"], rows["away_team"])
    rows["season_start"] = start
    rows["player_code"] = rows["element"].map(raw["players"].set_index("id")["code"])
    rows = rows.rename(columns={"GW": "gameweek", "value": "price"})
    for col in ("expected_goals", "expected_goals_conceded"):
        rows[col] = pd.to_numeric(rows[col], errors="raise")
    rows, missing_gws = mask_missing_lineups(rows)
    out = rows[OUTPUT_COLUMNS].sort_values(["kickoff", "match_id", "team", "element"]).reset_index(drop=True)

    recorded = out.dropna(subset=["starts"])
    starts = recorded.groupby(["match_id", "team"])["starts"].sum()
    xg_team = recorded.groupby(["match_id", "team"])["expected_goals"].sum()
    goals = pd.concat([linked.set_index(["match_id", "home_team"])["home_goals"].rename_axis(["match_id", "team"]),
                       linked.set_index(["match_id", "away_team"])["away_goals"].rename_axis(["match_id", "team"])])
    return out, {
        **link, **cleaning,
        "player_rows": int(len(out)), "players": int(out["element"].nunique()),
        "positions": sorted(out["position"].unique().tolist()),
        "team_side_mismatches": int((archive_team != rows["team"]).sum()),
        "players_without_code": int(out["player_code"].isna().sum()),
        "gameweeks": sorted(int(g) for g in out["gameweek"].unique()),
        "gameweeks_without_lineups": missing_gws,
        "team_matches_with_lineups": int(len(starts)),
        "starts_anomalies": [[m, t, int(v)] for (m, t), v in starts[starts != LINEUP_SIZE].items()],
        "team_matches_with_zero_xg": int((xg_team == 0).sum()),
        "xg_total_over_goals": float(xg_team.sum() / goals.loc[xg_team.index].sum()),
        "xg_negative": int((out["expected_goals"] < 0).sum()),
        "price_range": [int(out["price"].min()), int(out["price"].max())],
        "share_players_with_price_changes": float((out.groupby("element")["price"].nunique() > 1).mean()),
        "start_price": start_price_agreement(out, raw["players"]),
    }


# ------------------------------------------------------------------ controles

def assert_quality(start: int, r: dict) -> None:
    """Controles que, si fallan, invalidan las variables: se corta en vez de seguir con datos dudosos."""
    problems = []
    if r["fixtures"] != 380 or r["finished"] != 380:
        problems.append(f"partidos {r['fixtures']} (terminados {r['finished']})")
    if r["linked"] != 380:
        problems.append(f"vinculados {r['linked']}/380: {r['unlinked'][:3]}")
    if r["score_matches"] != r["linked"]:
        problems.append(f"marcadores distintos de Football-Data: {r['score_mismatches'][:3]}")
    if r["max_day_gap"] is None or r["max_day_gap"] > 1:
        problems.append(f"diferencia de fecha de {r['max_day_gap']} días")
    if r["team_side_mismatches"]:
        problems.append(f"{r['team_side_mismatches']} jugadores en el lado equivocado")
    if set(r["positions"]) - PLAYER_POSITIONS:
        problems.append(f"posiciones inesperadas {r['positions']}")
    if r["players_without_code"]:
        problems.append(f"{r['players_without_code']} filas sin código estable de jugador")
    # Las fechas sin titulares tienen que ser las primeras de las que existen: en 2022-23 el archivo no tiene
    # ningún partido con fecha 7 (los 380 están, asignados a otras fechas), así que la lista salta del 6 al 8.
    gws = r["gameweeks_without_lineups"]
    if gws != r["gameweeks"][:len(gws)]:
        problems.append(f"fechas sin titulares en el medio de la temporada: {gws}")
    if r["starts_anomalies"]:
        problems.append(f"equipos-partido sin 11 titulares: {r['starts_anomalies'][:3]}")
    if r["xg_negative"]:
        problems.append("xG negativo")
    if r["start_price"]["agreement"] < MIN_START_PRICE_AGREEMENT:
        problems.append(f"precio inicial coincide solo en {r['start_price']['agreement']:.1%}")
    if problems:
        raise ArchiveQualityError(f"{season_label(start)}: " + "; ".join(problems))


def verify_live(table: pd.DataFrame, season: int = FPL_SEASONS[-1], sample: int = 30, seed: int = 0) -> dict:
    """Contraste independiente con la API oficial: para una muestra de jugadores, el precio inicial de
    `season` según su historial oficial (element-summary, history_past.start_cost) contra el primer
    precio del archivo. Hace `sample` consultas; no forma parte del pipeline reproducible."""
    session = _session()
    current = session.get(f"{FPL_API}/bootstrap-static/", timeout=60).json()["elements"]
    first = (table[table.season_start == season].sort_values(["gameweek", "kickoff"])
             .groupby("player_code")["price"].first())
    candidates = [e for e in current if e["code"] in first.index]
    rng = np.random.default_rng(seed)
    picked = [candidates[i] for i in rng.choice(len(candidates), size=min(sample, len(candidates)), replace=False)]
    label, rows = season_label(season).replace("-", "/"), []      # "2025-26" -> "2025/26", como en la API
    for e in picked:
        past = session.get(f"{FPL_API}/element-summary/{e['id']}/", timeout=60).json()["history_past"]
        official = next((p["start_cost"] for p in past if p["season_name"] == label), None)
        if official is not None:
            rows.append((e["code"], int(first[e["code"]]), int(official)))
    agree = [a == b for _, a, b in rows]
    return {"season": season_label(season), "checked": len(rows), "agreement": float(np.mean(agree)) if rows else None,
            "disagree": [r for r, ok in zip(rows, agree) if not ok]}


def build(matches: pd.DataFrame, seasons: list[int] = FPL_SEASONS) -> tuple[pd.DataFrame, dict]:
    frames, report = [], {"source": f"https://github.com/{ARCHIVE_REPO}", "commit": ARCHIVE_COMMIT, "seasons": {}}
    for start in seasons:
        out, r = player_matches(start, read_season(start), matches)
        assert_quality(start, r)
        report["seasons"][season_label(start)] = r
        frames.append(out)
        logger.info("%s: %d filas · %d/380 partidos · marcadores iguales %d · sin titulares en fechas %s · "
                    "precio inicial %.1f%%", season_label(start), r["player_rows"], r["linked"], r["score_matches"],
                    r["gameweeks_without_lineups"] or "ninguna", 100 * r["start_price"]["agreement"])
    return pd.concat(frames, ignore_index=True), report


def main() -> None:
    from src.data.load import load_matches

    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Vuelve a descargar el archivo")
    parser.add_argument("--verify-live", action="store_true", help="Contrasta precios con la API oficial")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    hashes = download_archive(force=args.force)
    table, report = build(load_matches())
    report["files_sha256"] = hashes
    if args.verify_live:
        report["live_price_check"] = verify_live(table)
        logger.info("Contraste con la API oficial: %s", report["live_price_check"])
    table.to_parquet(PLAYER_MATCHES_PATH, index=False)
    QUALITY_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info("Guardado %s (%d filas) y %s", PLAYER_MATCHES_PATH, len(table), QUALITY_PATH)


if __name__ == "__main__":
    main()
