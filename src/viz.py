"""Estilo común para los gráficos estáticos (matplotlib) de notebooks y reportes.

Paleta: instancia de referencia validada para daltonismo (skill de dataviz).
Los tres primeros slots categóricos son distinguibles entre todos los pares
(no solo adyacentes), así que las tres eras de público usan esos tres.
"""

import matplotlib as mpl
import matplotlib.pyplot as plt

from src.eras import ERA_ORDER

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948",
)
CATEGORICAL = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED]
ERA_COLORS = dict(zip(ERA_ORDER, [BLUE, ORANGE, AQUA]))
OUTCOME_COLORS = {"H": BLUE, "D": ORANGE, "A": AQUA}
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def use_style() -> None:
    mpl.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "figure.dpi": 110,
        "savefig.dpi": 160,
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
        "font.size": 10,
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,
        "axes.titlesize": 12,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.titlepad": 22,  # deja lugar para subtitle()
        "axes.prop_cycle": mpl.cycler(color=CATEGORICAL),
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "lines.linewidth": 2,
        "lines.markersize": 5,
        "legend.frameon": False,
        "legend.fontsize": 9,
    })


def subtitle(ax: plt.Axes, text: str) -> None:
    """Texto secundario debajo del título (la conclusión o la unidad)."""
    ax.text(0, 1.01, text, transform=ax.transAxes, fontsize=9, color=INK_2, va="bottom")
