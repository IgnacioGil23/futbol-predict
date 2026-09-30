"""Valor de mercado de los planteles (Transfermarkt) en la fecha de cada partido.

Fuente: https://github.com/dcaribou/transfermarkt-datasets (repositorio CC0; los datos vienen de Transfermarkt, cuyos
términos no se revisaron). Como Football-Data, se descarga y NO se versiona; solo se publican agregados. El propio
proyecto informa que su recolección se detuvo a mediados de julio de 2026: las valuaciones llegan hasta el 12/06/2026
y no cubre 2026-27. Sirve para pruebas históricas, no para producción.

Plantel de un club en la fecha D (todo con eventos ANTERIORES a D):
* club de cada jugador = el del evento más reciente entre sus transferencias (club de destino) y sus valuaciones
  (club al momento de valuarlo): las valuaciones cubren a los formados en el club, que nunca figuran transferidos;
* valor = el más reciente entre valuaciones y el valor registrado al transferirse (así un fichaje cuenta desde que
  llega);
* se descartan los jugadores cuyo último evento tiene más de STALE_DAYS días (retirados o sin seguimiento);
* valor del plantel = suma de los TOP_PLAYERS valores más altos.

Los clubes se vinculan con los nombres de Football-Data por los partidos de liga (misma fecha y mismo marcador):
cada club de Transfermarkt se asigna al nombre con el que coincide en la mayoría de sus partidos y se verifica que
todos los partidos queden vinculados.

Uso:
    python -m src.data.transfermarkt
"""

import argparse
import json
import logging
from datetime import date

import numpy as np
import pandas as pd

from src.config import PROCESSED_DIR, PROJECT_ROOT, RAW_DIR
from src.data.download import _fetch, _session

logger = logging.getLogger(__name__)

SOURCE = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/{table}.csv.gz"
TABLES = ("player_valuations", "transfers", "games", "clubs")
TM_DIR = RAW_DIR / "transfermarkt"
SQUAD_VALUES_PATH = PROCESSED_DIR / "leagues" / "squad_values.parquet"
QUALITY_PATH = PROJECT_ROOT / "reports" / "transfermarkt" / "calidad_transfermarkt.json"
COMPETITIONS = {"ENG": ("GB1", "E0"), "ESP": ("ES1", "SP1"), "ITA": ("IT1", "I1"), "GER": ("L1", "D1"),
                "FRA": ("FR1", "F1")}
FIRST_SEASON = 2012                 # primera temporada con partidos de Transfermarkt para vincular clubes
STALE_DAYS = 400
TOP_PLAYERS = 25


def download(force: bool = False) -> dict[str, int]:
    session, sizes = _session(), {}
    for table in TABLES:
        path = TM_DIR / f"{table}.csv.gz"
        if force or not path.exists():
            sizes[table] = _fetch(session, SOURCE.format(table=table), path)
    return sizes


def read(table: str, **kwargs) -> pd.DataFrame:
    return pd.read_csv(TM_DIR / f"{table}.csv.gz", **kwargs)


# ------------------------------------------------------------------ vínculo de clubes

def link_clubs(games: pd.DataFrame, matches: pd.DataFrame, competition: str, division: str) -> tuple[dict, dict]:
    """club_id de Transfermarkt -> nombre de Football-Data, por partidos con la misma fecha y el mismo marcador."""
    g = games[games.competition_id == competition].copy()
    g["date"] = pd.to_datetime(g["date"])
    m = matches[(matches.division == division) & (matches.season_start >= FIRST_SEASON)
                & matches.home_goals.notna()].copy()
    m["date"] = pd.to_datetime(m["date"])
    j = m.merge(g, left_on=["date", "home_goals", "away_goals"], right_on=["date", "home_club_goals", "away_club_goals"])
    votes = pd.concat([j[["home_club_id", "home_team"]].set_axis(["club_id", "team"], axis=1),
                       j[["away_club_id", "away_team"]].set_axis(["club_id", "team"], axis=1)])
    mapping = votes.groupby("club_id")["team"].agg(lambda s: s.value_counts().index[0]).to_dict()
    # verificación: cada partido de Football-Data tiene que tener exactamente un partido de Transfermarkt con sus clubes
    g["home_team"], g["away_team"] = g["home_club_id"].map(mapping), g["away_club_id"].map(mapping)
    linked = m.merge(g[["date", "home_team", "away_team", "home_club_goals", "away_club_goals"]],
                     on=["date", "home_team", "away_team"], how="left")
    ok = linked["home_club_goals"].notna()
    same = ok & (linked["home_club_goals"] == linked["home_goals"]) & (linked["away_club_goals"] == linked["away_goals"])
    teams = set(m.home_team) | set(m.away_team)
    return mapping, {"matches": int(len(m)), "linked": int(ok.sum()), "same_score": int(same.sum()),
                     "teams": len(teams), "teams_mapped": len(teams & set(mapping.values())),
                     "clubs_to_one_team": bool(pd.Series(mapping).value_counts().max() == 1)}


# ------------------------------------------------------------------ plantel en cada fecha

def player_events(valuations: pd.DataFrame, transfers: pd.DataFrame) -> pd.DataFrame:
    """Línea de tiempo por jugador: fecha, club (si el evento lo dice) y valor (si el evento lo dice)."""
    # order: en el mismo día, la transferencia (club nuevo) va después de la valuación
    v = pd.DataFrame({"player_id": valuations["player_id"], "date": pd.to_datetime(valuations["date"]),
                      "club_id": valuations["current_club_id"], "value": valuations["market_value_in_eur"], "order": 0})
    t = pd.DataFrame({"player_id": transfers["player_id"], "date": pd.to_datetime(transfers["transfer_date"]),
                      "club_id": transfers["to_club_id"], "value": transfers["market_value_in_eur"], "order": 1})
    ev = pd.concat([v, t], ignore_index=True).dropna(subset=["date"])
    ev = ev.sort_values(["player_id", "date", "order"]).reset_index(drop=True)
    g = ev.groupby("player_id")
    ev["club_id"] = g["club_id"].ffill()
    ev["value"] = g["value"].ffill()
    ev["valid_to"] = g["date"].shift(-1).fillna(pd.Timestamp("2100-01-01"))
    return ev.dropna(subset=["club_id", "value"])[["player_id", "date", "valid_to", "club_id", "value"]]


def squad_value(events: pd.DataFrame, club_id: int, dates: np.ndarray) -> np.ndarray:
    """Valor del plantel del club en cada fecha (eventos estrictamente anteriores a la fecha)."""
    e = events[events.club_id == club_id]
    start, end = e["date"].to_numpy(), e["valid_to"].to_numpy()
    values = e["value"].to_numpy(float)
    out = np.full(len(dates), np.nan)
    for i, d in enumerate(dates):
        active = (start < d) & (end >= d) & (d - start <= np.timedelta64(STALE_DAYS, "D"))
        if active.any():
            out[i] = np.sort(values[active])[::-1][:TOP_PLAYERS].sum()
    return out


def match_squad_values(matches: pd.DataFrame, mapping: dict, events: pd.DataFrame, division: str) -> pd.DataFrame:
    m = matches[(matches.division == division) & (matches.season_start >= FIRST_SEASON)][
        ["match_id", "date", "season_start", "home_team", "away_team"]].copy()
    m["date"] = pd.to_datetime(m["date"])
    team_to_club = {t: c for c, t in mapping.items()}
    for side in ("home", "away"):
        m[f"squad_value_{side}"] = np.nan
    for team in sorted(set(m.home_team) | set(m.away_team)):
        club = team_to_club.get(team)
        if club is None:
            continue
        rows = (m.home_team == team) | (m.away_team == team)
        dates = np.sort(m.loc[rows, "date"].unique())
        values = pd.Series(squad_value(events, club, dates), index=pd.DatetimeIndex(dates))
        for side in ("home", "away"):
            sel = m[f"{side}_team"] == team
            m.loc[sel, f"squad_value_{side}"] = values.loc[m.loc[sel, "date"]].to_numpy()
    return m


def main() -> None:
    from src.data.leagues import matches_path
    from src.data.load import load_matches

    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    download(force=args.force)
    games = read("games", usecols=["competition_id", "date", "home_club_id", "away_club_id", "home_club_goals",
                                   "away_club_goals"])
    events = player_events(read("player_valuations"), read("transfers"))
    frames, report = [], {"generated": date.today().isoformat(), "stale_days": STALE_DAYS, "top_players": TOP_PLAYERS,
                          "last_valuation": str(pd.to_datetime(read("player_valuations")["date"]).max().date()),
                          "leagues": {}}
    for code, (competition, division) in COMPETITIONS.items():
        matches = load_matches() if code == "ENG" else pd.read_parquet(matches_path(code))
        mapping, link = link_clubs(games, matches, competition, division)
        values = match_squad_values(matches, mapping, events, division)
        values["league"] = code
        per_season = values.groupby("season_start")[["squad_value_home", "squad_value_away"]].apply(
            lambda g: float(g.notna().all(axis=1).mean()))
        report["leagues"][code] = {**link, "coverage_by_season": {str(k): v for k, v in per_season.items()},
                                   "mapping": {str(k): v for k, v in sorted(mapping.items(), key=lambda x: x[1])}}
        frames.append(values)
        logger.info("%s: %d/%d partidos vinculados (marcador igual %d) · %d/%d equipos · cobertura mínima %.1f%%",
                    code, link["linked"], link["matches"], link["same_score"], link["teams_mapped"], link["teams"],
                    100 * per_season.min())
    SQUAD_VALUES_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_parquet(SQUAD_VALUES_PATH, index=False)
    QUALITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUALITY_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Guardado %s y %s", SQUAD_VALUES_PATH, QUALITY_PATH)


if __name__ == "__main__":
    main()
