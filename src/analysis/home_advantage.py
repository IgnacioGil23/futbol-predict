"""Ventaja de local por temporada y por era de público (mismo cálculo que notebooks/01_eda)."""

import numpy as np
import pandas as pd

from src import eras


def bootstrap_mean_ci(values, n_boot: int = 10_000, seed: int = 42) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    boots = values[rng.integers(0, len(values), size=(n_boot, len(values)))].mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(lo), float(hi)


def home_advantage(pl: pd.DataFrame, n_boot: int = 10_000) -> dict:
    """`pl`: partidos jugados de Premier League (date, season, home_goals, away_goals, result)."""
    df = pl.copy()
    df["goal_diff"] = df["home_goals"].astype(float) - df["away_goals"].astype(float)
    df["era"] = eras.assign_era(df["date"])
    result = df["result"].astype(str)

    def block(g: pd.DataFrame) -> dict:
        r = g["result"].astype(str)
        lo, hi = bootstrap_mean_ci(g["goal_diff"], n_boot)
        return {
            "matches": int(len(g)),
            "home_win": float((r == "H").mean()), "draw": float((r == "D").mean()), "away_win": float((r == "A").mean()),
            "goal_diff": float(g["goal_diff"].mean()), "goal_diff_ci": [lo, hi],
        }

    return {
        "eras": [{"era": era, **block(df[df.era == era]),
                  "from": df.loc[df.era == era, "date"].min().date().isoformat(),
                  "to": df.loc[df.era == era, "date"].max().date().isoformat()} for era in eras.ERA_ORDER],
        "seasons": [{"season": s, **block(g)} for s, g in df.groupby("season", sort=True)],
        "overall_home_win": float((result == "H").mean()),
    }
