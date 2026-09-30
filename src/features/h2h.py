"""Head-to-head suavizado.

El historial directo crudo ("el local ganó 4 de los últimos 6") confunde el
cruce con la diferencia de fuerza: si A es mucho mejor que B, A gana los cruces
por ser mejor, no por el cruce. Lo que puede aportar información nueva es si,
en ese cruce, un equipo rinde sistemáticamente POR ENCIMA de lo que su Elo
predecía. Por eso se usa el residuo de Elo:

    residuo de un cruce previo = puntaje real - puntaje esperado por Elo
                                 (desde la perspectiva del local del partido actual)

    h2h_residual = suma de residuos / (n + m)

El término m contrae hacia 0 cuando hay pocos cruces (con m = 5 y 1 cruce previo,
se conserva solo 1/6 de ese residuo). Solo se usan cruces jugados en días
anteriores al partido, en Premier o Championship.
"""

import numpy as np
import pandas as pd


def h2h_features(matches: pd.DataFrame, elo: pd.DataFrame, shrinkage: float = 5.0) -> pd.DataFrame:
    """Devuelve match_id, h2h_n (cruces previos) y h2h_residual (perspectiva del local)."""
    df = matches[["match_id", "date", "home_team", "away_team", "home_goals", "away_goals"]].merge(
        elo[["match_id", "elo_expected_home"]], on="match_id", how="left"
    )
    df = df.sort_values(["date", "match_id"]).reset_index(drop=True)
    df["home_goals"] = df["home_goals"].astype("float64")  # Int64 con pd.NA -> float con NaN
    df["away_goals"] = df["away_goals"].astype("float64")
    played = df["home_goals"].notna() & df["away_goals"].notna()
    alpha = np.where(df.home_goals > df.away_goals, 1.0, np.where(df.home_goals == df.away_goals, 0.5, 0.0))
    # Residuo desde la perspectiva del equipo que va primero en orden alfabético.
    first_is_home = df["home_team"] < df["away_team"]
    resid_home = alpha - df["elo_expected_home"].to_numpy()
    df["pair"] = np.where(first_is_home, df.home_team + "|" + df.away_team, df.away_team + "|" + df.home_team)
    df["resid_first"] = np.where(first_is_home, resid_home, -resid_home)
    df.loc[~played, "resid_first"] = np.nan

    # Acumulados por par y día: se agregan por fecha para que un cruce no se vea a sí mismo
    # (y por robustez, aunque un par no juega dos veces el mismo día).
    daily = (df[played].groupby(["pair", "date"])
             .agg(n=("resid_first", "size"), s=("resid_first", "sum")).reset_index())
    daily[["cum_n", "cum_s"]] = daily.groupby("pair")[["n", "s"]].cumsum()
    left = df[["match_id", "pair", "date"]].sort_values("date")
    right = daily[["pair", "date", "cum_n", "cum_s"]].rename(columns={"date": "state_date"}).sort_values("state_date")
    merged = pd.merge_asof(left, right, left_on="date", right_on="state_date", by="pair",
                           direction="backward", allow_exact_matches=False)
    merged = merged.set_index("match_id").loc[df["match_id"]].reset_index()
    n = merged["cum_n"].fillna(0).to_numpy()
    s = merged["cum_s"].fillna(0.0).to_numpy()
    residual_first = s / (n + shrinkage)
    return pd.DataFrame({
        "match_id": df["match_id"],
        "h2h_n": n.astype(int),
        "h2h_residual": np.where(first_is_home, residual_first, -residual_first),
    })
