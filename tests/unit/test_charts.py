from __future__ import annotations

from src.pipeline.actions import _charts


def test_scale_degenerate_range_returns_midpoint():
    assert _charts._scale(5.0, 3.0, 3.0, 0.0, 100.0) == 50.0


def test_scale_normal_range():
    assert _charts._scale(5.0, 0.0, 10.0, 0.0, 100.0) == 50.0


def test_write_line_chart_svg_no_points_returns_none(tmp_path):
    result = _charts.write_line_chart_svg(tmp_path / "empty.svg", "t", "x", "y", lines={})
    assert result is None
    assert not (tmp_path / "empty.svg").exists()


def test_write_line_chart_svg_single_point_degenerate_axes(tmp_path):
    path = _charts.write_line_chart_svg(
        tmp_path / "single.svg", "t", "x", "y", lines={"only": [(1.0, 1.0)]}
    )
    assert path is not None
    assert path.exists()
    assert "<svg" in path.read_text(encoding="utf-8")


def test_write_line_chart_svg_with_markers(tmp_path):
    path = _charts.write_line_chart_svg(
        tmp_path / "marked.svg",
        "t",
        "x",
        "y",
        lines={"a": [(0.0, 1.0), (1.0, 2.0)], "b": [(0.0, -1.0), (1.0, 0.5)]},
        markers=[(0.5, 1.5)],
    )
    content = path.read_text(encoding="utf-8")
    assert "stroke=\"red\"" in content
    assert "exceção" in content


def test_write_stability_elasticity_chart_no_isolated_rows_returns_none(tmp_path):
    rows = [{"metrica": "VaR", "cenario": "conjunto", "fator": "usdbrl", "choque": 0.05, "elasticidade": 1.0}]
    assert _charts.write_stability_elasticity_chart(tmp_path, "run1", rows) is None


def test_write_stability_elasticity_chart_picks_top_factors(tmp_path):
    rows = [
        {"metrica": "VaR", "cenario": "isolado", "fator": "usdbrl", "choque": 0.01, "elasticidade": 0.5},
        {"metrica": "VaR", "cenario": "isolado", "fator": "usdbrl", "choque": 0.05, "elasticidade": 0.6},
        {"metrica": "VaR", "cenario": "isolado", "fator": "wti", "choque": 0.01, "elasticidade": 0.01},
    ]
    path = _charts.write_stability_elasticity_chart(tmp_path, "run1", rows, top_n=1)
    assert path is not None
    assert path.name == "stability_elasticity.svg"
    content = path.read_text(encoding="utf-8")
    assert "usdbrl" in content
    assert "wti" not in content  # top_n=1 exclui o fator menos relevante


def test_write_backtest_exceptions_chart_no_h1_series_returns_none(tmp_path):
    rows = [{"metrica": "VaR", "holding_period": 10, "series": None}]
    assert _charts.write_backtest_exceptions_chart(tmp_path, "run1", rows) is None


def test_write_backtest_exceptions_chart_draws_series(tmp_path):
    rows = [
        {
            "metrica": "VaR",
            "holding_period": 1,
            "series": {
                "indices": [250, 251, 252],
                "var_h": [10.0, 10.0, 10.0],
                "realized_loss": [5.0, 12.0, -3.0],
                "exceedances": [False, True, False],
            },
        }
    ]
    path = _charts.write_backtest_exceptions_chart(tmp_path, "run1", rows)
    assert path is not None
    assert path.name == "backtest_exceptions.svg"
    content = path.read_text(encoding="utf-8")
    assert "VaR" in content
    assert "exceção" in content
