"""Registro inmutable de predicciones (monitoreo del modelo).

Antes de cada partido de Premier League se guarda exactamente lo que el modelo
predijo, una sola vez por partido, para poder evaluarlo contra el resultado real
sin posibilidad de "retocar" predicciones después.

Reglas:
* Clave del partido: (temporada, local, visitante). Cada cruce ocurre una sola vez
  por temporada, así que la clave sobrevive a partidos reprogramados.
* Solo se registran partidos con fecha POSTERIOR al día de la corrida (UTC): así
  la predicción siempre es anterior al inicio del partido.
* La primera predicción de un partido es la definitiva: corridas posteriores no la
  reemplazan.
* Solo se agrega texto al final del archivo; `verify_append_only` comprueba que el
  contenido anterior siga intacto byte por byte.
* `source` distingue "vivo" (registrado antes del partido) de "reconstruido"
  (predicción fuera de muestra calculada después, usada solo para arrancar el
  historial y marcada como tal).

Uso (lo corre el workflow diario):
    python -m src.monitoring.ledger --ledger monitoring/ledger/predictions.csv
"""

import argparse
import io
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import season_label, season_start_year
from src.data.fixtures import fetch_fixtures
from src.odds import shin_probabilities
from src.serving.predictor import EloPoissonPredictor
from src.serving.store import MatchStore

logger = logging.getLogger(__name__)

DEFAULT_LEDGER = Path("monitoring/ledger/predictions.csv")
KEY = ["season_start", "home_team", "away_team"]
COLUMNS = [
    "season", "season_start", "home_team", "away_team", "match_date", "kickoff_time",
    "logged_at_utc", "source", "model_version", "code_commit",
    "elo_home", "elo_away", "elo_data_until",
    "lam", "mu", "p_home", "p_draw", "p_away", "top_scores",
    "b365_home", "b365_draw", "b365_away", "market_home", "market_draw", "market_away",
]
FLOAT_FORMAT = "%.6f"


class LedgerIntegrityError(RuntimeError):
    """El registro existente fue modificado (no es un agregado al final)."""


def read_ledger(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, dtype={"home_team": str, "away_team": str, "season": str, "source": str,
                                  "model_version": str, "code_commit": str, "kickoff_time": str})
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise LedgerIntegrityError(f"Faltan columnas en el registro: {sorted(missing)}")
    return df[COLUMNS]


def _top_scores(matrix: np.ndarray, k: int = 5) -> str:
    n = matrix.shape[1]
    idx = np.argsort(matrix, axis=None)[::-1][:k]
    return "|".join(f"{i // n}-{i % n}:{matrix.flat[i]:.4f}" for i in idx)


def _market(odds: list[float]) -> list[float]:
    arr = np.asarray(odds, dtype=float)
    if np.isnan(arr).any() or (arr <= 1).any():
        return [np.nan, np.nan, np.nan]
    return shin_probabilities(arr[None, :])[0].tolist()


def prediction_row(predictor: EloPoissonPredictor, *, home: str, away: str, match_date: pd.Timestamp,
                   elo_home: float, elo_away: float, elo_data_until: str, odds: list[float],
                   logged_at: datetime, source: str, code_commit: str, kickoff_time: str | None = None) -> dict:
    pred = predictor.predict(elo_home, elo_away)
    market = _market(odds)
    start = season_start_year(match_date.date())
    return {
        "season": season_label(start), "season_start": start, "home_team": home, "away_team": away,
        "match_date": match_date.date().isoformat(), "kickoff_time": kickoff_time or "",
        "logged_at_utc": logged_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "source": source, "model_version": predictor.version, "code_commit": code_commit,
        "elo_home": elo_home, "elo_away": elo_away, "elo_data_until": elo_data_until,
        "lam": pred.lam, "mu": pred.mu,
        "p_home": pred.probs[0], "p_draw": pred.probs[1], "p_away": pred.probs[2],
        "top_scores": _top_scores(pred.matrix),
        "b365_home": odds[0], "b365_draw": odds[1], "b365_away": odds[2],
        "market_home": market[0], "market_draw": market[1], "market_away": market[2],
    }


def new_live_entries(fixtures: pd.DataFrame, store: MatchStore, predictor: EloPoissonPredictor,
                     existing: pd.DataFrame, now: datetime, code_commit: str) -> pd.DataFrame:
    """Predicciones a registrar: partidos con fecha posterior a hoy (UTC) que todavía no estén en el registro."""
    today = now.astimezone(timezone.utc).date()
    logged = set(map(tuple, existing[KEY].astype(str).to_numpy())) if len(existing) else set()
    played = store.matches[store.matches.home_goals.notna()]
    data_until = played.date.max().date().isoformat() if len(played) else ""
    rows = []
    for f in fixtures.itertuples(index=False):
        day = pd.Timestamp(f.date)
        if day.date() <= today:
            continue  # el partido es hoy o ya pasó: registrarlo ahora no garantizaría ser pre-partido
        key = (str(season_start_year(day.date())), f.HomeTeam, f.AwayTeam)
        if key in logged:
            continue
        try:
            elo_h, elo_a = store.elo_as_of(f.HomeTeam, day), store.elo_as_of(f.AwayTeam, day)
        except KeyError:
            logger.warning("Equipo desconocido en fixtures, no se registra: %s vs %s", f.HomeTeam, f.AwayTeam)
            continue
        if elo_h is None or elo_a is None:
            logger.warning("Sin Elo para %s vs %s, no se registra", f.HomeTeam, f.AwayTeam)
            continue
        rows.append(prediction_row(
            predictor, home=f.HomeTeam, away=f.AwayTeam, match_date=day, elo_home=elo_h, elo_away=elo_a,
            elo_data_until=data_until, odds=[f.B365H, f.B365D, f.B365A], logged_at=now, source="vivo",
            code_commit=code_commit, kickoff_time=str(getattr(f, "Time", "") or "")))
        logged.add(key)
    return pd.DataFrame(rows, columns=COLUMNS)


def serialize_rows(rows: pd.DataFrame, header: bool) -> str:
    buf = io.StringIO()
    rows[COLUMNS].to_csv(buf, index=False, header=header, float_format=FLOAT_FORMAT, lineterminator="\n")
    return buf.getvalue()


def verify_append_only(old_text: str, new_text: str) -> None:
    if not new_text.startswith(old_text):
        raise LedgerIntegrityError("El registro existente cambió: solo se permite agregar filas al final.")


def append_entries(path: Path, entries: pd.DataFrame) -> int:
    """Agrega filas al final del archivo (sin reescribir lo existente) y verifica la integridad."""
    old_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if entries.empty:
        return 0
    existing = read_ledger(path)
    keys = set(map(tuple, existing[KEY].astype(str).to_numpy())) if len(existing) else set()
    dupes = [k for k in map(tuple, entries[KEY].astype(str).to_numpy()) if k in keys]
    if dupes or entries.duplicated(KEY).any():
        raise LedgerIntegrityError(f"Partidos ya registrados o repetidos: {dupes[:3]}")
    entries = entries.sort_values(["match_date", "home_team"])
    new_text = old_text + serialize_rows(entries, header=not old_text)
    verify_append_only(old_text, new_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8", newline="\n")
    return len(entries)


def reconstructed_entries(review_matches: list[dict], predictor: EloPoissonPredictor, existing: pd.DataFrame,
                          now: datetime, code_commit: str, data_until: str) -> pd.DataFrame:
    """Partidos ya jugados de la temporada en curso, con su predicción fuera de muestra (source="reconstruido").

    Sirve solo para que el historial no arranque vacío: se usa el Elo previo a cada
    partido y el modelo de producción (entrenado con temporadas anteriores). Se
    marca explícitamente porque NO se registró antes del partido.
    """
    logged = set(map(tuple, existing[KEY].astype(str).to_numpy())) if len(existing) else set()
    rows = []
    for m in review_matches:
        day = pd.Timestamp(m["date"])
        key = (str(season_start_year(day.date())), m["home_team"], m["away_team"])
        if key in logged:
            continue
        rows.append(prediction_row(
            predictor, home=m["home_team"], away=m["away_team"], match_date=day,
            elo_home=m["elo"][0], elo_away=m["elo"][1], elo_data_until=data_until,
            odds=[np.nan, np.nan, np.nan], logged_at=now, source="reconstruido", code_commit=code_commit))
        if m.get("market"):
            rows[-1].update({"market_home": m["market"][0], "market_draw": m["market"][1], "market_away": m["market"][2]})
    return pd.DataFrame(rows, columns=COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Registra predicciones de próximos partidos")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--seed-reconstructed", type=Path, default=None,
                        help="JSON de revisión de la temporada en curso (web/public/data/review/AAAA-AA.json)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    now = datetime.now(timezone.utc)
    commit = os.getenv("GITHUB_SHA", "local")[:12]
    store, predictor = MatchStore.load(), EloPoissonPredictor.load()
    existing = read_ledger(args.ledger)

    if args.seed_reconstructed:
        import json
        review = json.loads(args.seed_reconstructed.read_text(encoding="utf-8"))["matches"]
        played = store.matches[store.matches.home_goals.notna()]
        entries = reconstructed_entries(review, predictor, existing, now, commit,
                                        played.date.max().date().isoformat())
        logger.info("Reconstruidas: %d", append_entries(args.ledger, entries))
        return

    fixtures = fetch_fixtures()
    entries = new_live_entries(fixtures, store, predictor, existing, now, commit)
    added = append_entries(args.ledger, entries)
    logger.info("Próximos partidos publicados: %d · registrados ahora: %d · total en el registro: %d",
                len(fixtures), added, len(existing) + added)


if __name__ == "__main__":
    main()
