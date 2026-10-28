"""Resúmenes que la web muestra como texto: se calculan en la exportación, no se escriben a mano."""

import numpy as np
from scipy.stats import poisson

from src.export.site import top_score_probability


def test_top_score_probability_matches_the_full_grid_maximum():
    for lam, mu in [(0.4, 2.7), (1.0, 1.0), (1.55, 1.12), (3.2, 0.25)]:
        goals = np.arange(15)
        grid = np.outer(poisson.pmf(goals, lam), poisson.pmf(goals, mu))
        assert np.isclose(top_score_probability(lam, mu), grid.max())


def test_top_score_probability_is_vectorized():
    out = top_score_probability([1.2, 2.0], [0.8, 1.5])
    assert out.shape == (2,) and np.all((out > 0) & (out < 1))


def test_write_turns_every_nan_into_null(tmp_path):
    from src.export.site import write
    write(tmp_path / "x.json", {"kickoff_ar": float("nan"), "p": np.float64("nan"), "v": [1.5, float("nan")]})
    assert (tmp_path / "x.json").read_text(encoding="utf-8") == '{"kickoff_ar":null,"p":null,"v":[1.5,null]}'


def test_one_failing_league_does_not_stop_the_others(tmp_path, monkeypatch):
    import json

    import src.export.site as site

    class Ctx:
        def __init__(self, code):
            self.code = code

    monkeypatch.setattr(site, "premier_context", lambda: Ctx("ENG"))
    monkeypatch.setattr(site, "league_context", lambda code: Ctx(code))
    monkeypatch.setattr(site, "leagues_index", lambda ctxs: [c.code for c in ctxs])

    def export(out, ctx, today):
        if ctx.code == "ESP":
            raise ValueError("calendario roto")
    monkeypatch.setattr(site, "export_league", export)
    monkeypatch.setattr("sys.argv", ["site", "--out", str(tmp_path), "--leagues", "ENG", "ESP", "ITA"])
    site.main()
    assert json.loads((tmp_path / "leagues.json").read_text(encoding="utf-8")) == ["ENG", "ITA"]
