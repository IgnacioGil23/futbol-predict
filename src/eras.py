"""Eras de público en estadios de la Premier League (COVID-19).

Fechas verificadas (29/09/2026):
* 13/03/2020: suspensión del torneo. Reanudación a puerta cerrada el 17/06/2020
  (Aston Villa-Sheffield United y Man City-Arsenal); la temporada 2019/20 cerró
  el 26/07/2020.  https://en.wikipedia.org/wiki/2019%E2%80%9320_Premier_League
* 2020/21 (12/09/2020 - 23/05/2021), casi toda a puerta cerrada, con dos
  ventanas de público limitado: desde el 02/12/2020 en zonas de bajo riesgo
  (hasta el confinamiento anunciado el 04/01/2021) y desde el 17/05/2021 con un
  máximo de 10.000 espectadores o 25% del aforo.
  https://en.wikipedia.org/wiki/2020%E2%80%9321_Premier_League
* 2021/22 arrancó el 13/08/2021 con aforo completo.
  https://en.wikipedia.org/wiki/2021%E2%80%9322_Premier_League

Ni siquiera dentro de las ventanas de público limitado todos los partidos
tuvieron público (dependía de la zona sanitaria de cada estadio); el dataset no
trae asistencia por partido, así que esas ventanas se marcan aparte para poder
excluirlas en un análisis de sensibilidad en vez de asignarlas a una era.
"""

import pandas as pd

PRE_PANDEMIC = "Con público (hasta mar-2020)"
NO_CROWDS = "Sin público (jun-2020 a may-2021)"
FULL_CROWDS = "Con público (desde ago-2021)"
ERA_ORDER = [PRE_PANDEMIC, NO_CROWDS, FULL_CROWDS]

SUSPENSION = pd.Timestamp("2020-03-13")
RESTART = pd.Timestamp("2020-06-17")
NO_CROWDS_END = pd.Timestamp("2021-05-23")
FULL_CAPACITY_RETURN = pd.Timestamp("2021-08-13")

# Ventanas dentro de la era "sin público" en las que algunos estadios admitieron
# público limitado.
PARTIAL_CROWD_WINDOWS = (
    (pd.Timestamp("2020-12-02"), pd.Timestamp("2021-01-03")),
    (pd.Timestamp("2021-05-17"), pd.Timestamp("2021-05-23")),
)


def assign_era(dates: pd.Series) -> pd.Series:
    """Era de público para cada fecha; NaN fuera de las tres eras (no debería pasar en E0)."""
    dates = pd.to_datetime(dates)
    era = pd.Series(pd.NA, index=dates.index, dtype="string")
    era[dates < SUSPENSION] = PRE_PANDEMIC
    era[(dates >= RESTART) & (dates <= NO_CROWDS_END)] = NO_CROWDS
    era[dates >= FULL_CAPACITY_RETURN] = FULL_CROWDS
    return era


def in_partial_crowd_window(dates: pd.Series) -> pd.Series:
    dates = pd.to_datetime(dates)
    mask = pd.Series(False, index=dates.index)
    for start, end in PARTIAL_CROWD_WINDOWS:
        mask |= (dates >= start) & (dates <= end)
    return mask
