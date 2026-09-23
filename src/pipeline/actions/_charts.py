"""Geração de gráficos do relatório final (CLAUDE.md §9.2).

`matplotlib` não está nas dependências base assumidas (§2.2: só stdlib +
numpy + pandas) e não está instalado neste ambiente — por isso os gráficos
são desenhados manualmente como SVG (linhas/eixos/marcadores em coordenadas
de pixel calculadas em Python puro + escrita direta do XML do SVG), conforme
o fallback explicitamente previsto em §9.2, em vez de simplesmente omitir a
imagem.

Nenhuma função aqui inventa dados: cada uma recebe as linhas já lidas de
`memory/state.db` (via `MemoryStore.read_outputs`) e só desenha o que já foi
persistido pelas Actions 07/08.
"""

from __future__ import annotations

from pathlib import Path

_WIDTH = 760
_HEIGHT = 420
_MARGIN_LEFT = 70
_MARGIN_RIGHT = 30
_MARGIN_TOP = 40
_MARGIN_BOTTOM = 60
_PLOT_W = _WIDTH - _MARGIN_LEFT - _MARGIN_RIGHT
_PLOT_H = _HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM
_PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#ea580c", "#7c3aed", "#0891b2"]


def _scale(value: float, vmin: float, vmax: float, out_min: float, out_max: float) -> float:
    if vmax == vmin:
        return (out_min + out_max) / 2.0
    return out_min + (value - vmin) / (vmax - vmin) * (out_max - out_min)


def _svg_header(title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{_HEIGHT}" '
        f'viewBox="0 0 {_WIDTH} {_HEIGHT}" font-family="sans-serif">',
        f'<rect x="0" y="0" width="{_WIDTH}" height="{_HEIGHT}" fill="white"/>',
        f'<text x="{_WIDTH / 2}" y="20" text-anchor="middle" font-size="15" font-weight="bold">{_escape(title)}</text>',
    ]


def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _axes(x_label: str, y_label: str, xmin: float, xmax: float, ymin: float, ymax: float) -> list[str]:
    x0 = _MARGIN_LEFT
    x1 = _MARGIN_LEFT + _PLOT_W
    y0 = _MARGIN_TOP + _PLOT_H
    y1 = _MARGIN_TOP
    parts = [
        f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="black" stroke-width="1"/>',
        f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="black" stroke-width="1"/>',
        f'<text x="{(x0 + x1) / 2}" y="{_HEIGHT - 12}" text-anchor="middle" font-size="12">{_escape(x_label)}</text>',
        f'<text x="14" y="{(y0 + y1) / 2}" text-anchor="middle" font-size="12" '
        f'transform="rotate(-90 14,{(y0 + y1) / 2})">{_escape(y_label)}</text>',
    ]
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        yv = ymin + frac * (ymax - ymin)
        ypix = _scale(yv, ymin, ymax, y0, y1)
        parts.append(f'<line x1="{x0 - 4}" y1="{ypix:.1f}" x2="{x0}" y2="{ypix:.1f}" stroke="black"/>')
        parts.append(f'<text x="{x0 - 8}" y="{ypix + 4:.1f}" text-anchor="end" font-size="10">{yv:.4g}</text>')
        xv = xmin + frac * (xmax - xmin)
        xpix = _scale(xv, xmin, xmax, x0, x1)
        parts.append(f'<line x1="{xpix:.1f}" y1="{y0}" x2="{xpix:.1f}" y2="{y0 + 4}" stroke="black"/>')
        parts.append(f'<text x="{xpix:.1f}" y="{y0 + 16}" text-anchor="middle" font-size="10">{xv:.4g}</text>')
    return parts


def _legend(labels_colors: list[tuple[str, str]]) -> list[str]:
    parts = []
    x = _MARGIN_LEFT
    y = _MARGIN_TOP - 18
    for label, color in labels_colors:
        parts.append(f'<line x1="{x}" y1="{y}" x2="{x + 16}" y2="{y}" stroke="{color}" stroke-width="2.5"/>')
        parts.append(f'<text x="{x + 20}" y="{y + 4}" font-size="10">{_escape(label)}</text>')
        x += 20 + 8 * len(label) + 20
    return parts


def write_line_chart_svg(
    path: Path,
    title: str,
    x_label: str,
    y_label: str,
    lines: dict[str, list[tuple[float, float]]],
    markers: list[tuple[float, float]] | None = None,
) -> Path | None:
    """Desenha um gráfico de linhas simples em SVG puro. `lines` é
    `{legenda: [(x, y), ...]}`; `markers` (opcional) marca pontos extras
    (ex.: exceções de backtest) com um X vermelho por cima das linhas."""
    all_points = [pt for series in lines.values() for pt in series]
    if markers:
        all_points = all_points + markers
    if not all_points:
        return None

    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmin == xmax:
        xmin, xmax = xmin - 1, xmax + 1
    if ymin == ymax:
        ymin, ymax = ymin - 1, ymax + 1
    # folga de 8% no eixo Y para os pontos não colarem na borda
    pad = 0.08 * (ymax - ymin)
    ymin, ymax = ymin - pad, ymax + pad

    x0, x1 = _MARGIN_LEFT, _MARGIN_LEFT + _PLOT_W
    y0, y1 = _MARGIN_TOP + _PLOT_H, _MARGIN_TOP

    svg = _svg_header(title)
    svg += _axes(x_label, y_label, xmin, xmax, ymin, ymax)

    legend_entries = []
    for idx, (label, points) in enumerate(sorted(lines.items())):
        color = _PALETTE[idx % len(_PALETTE)]
        legend_entries.append((label, color))
        points_sorted = sorted(points, key=lambda p: p[0])
        poly = " ".join(
            f"{_scale(px, xmin, xmax, x0, x1):.1f},{_scale(py, ymin, ymax, y0, y1):.1f}" for px, py in points_sorted
        )
        svg.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2"/>')
        for px, py in points_sorted:
            cx, cy = _scale(px, xmin, xmax, x0, x1), _scale(py, ymin, ymax, y0, y1)
            svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.5" fill="{color}"/>')

    if markers:
        for mx, my in markers:
            cx, cy = _scale(mx, xmin, xmax, x0, x1), _scale(my, ymin, ymax, y0, y1)
            svg.append(
                f'<line x1="{cx - 5:.1f}" y1="{cy - 5:.1f}" x2="{cx + 5:.1f}" y2="{cy + 5:.1f}" stroke="red" stroke-width="2"/>'
            )
            svg.append(
                f'<line x1="{cx - 5:.1f}" y1="{cy + 5:.1f}" x2="{cx + 5:.1f}" y2="{cy - 5:.1f}" stroke="red" stroke-width="2"/>'
            )
        legend_entries.append(("exceção", "red"))

    svg += _legend(legend_entries)
    svg.append("</svg>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(svg), encoding="utf-8")
    return path


def write_stability_elasticity_chart(assets_dir: Path, run_id: str, stability_rows: list[dict], top_n: int = 5) -> Path | None:
    """Elasticidade × magnitude de choque, para os `top_n` pares
    (métrica, fator) com maior |elasticidade| máxima observada — os "casos
    mais relevantes ou mais problemáticos" pedidos em §9.2. Só usa cenário
    `isolado` (o choque conjunto e a quebra de correlação não têm uma única
    "magnitude de choque" comparável no mesmo eixo)."""
    by_pair: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for row in stability_rows:
        if row.get("cenario") != "isolado" or row.get("choque") is None or row.get("elasticidade") is None:
            continue
        key = (row["metrica"], row["fator"])
        by_pair.setdefault(key, []).append((float(row["choque"]) * 100.0, float(row["elasticidade"])))

    if not by_pair:
        return None

    ranked = sorted(by_pair.items(), key=lambda kv: max(abs(y) for _, y in kv[1]), reverse=True)[:top_n]
    lines = {f"{metrica} / {fator}": points for (metrica, fator), points in ranked}

    path = assets_dir / run_id / "stability_elasticity.svg"
    return write_line_chart_svg(
        path,
        title="Testes de estabilidade — elasticidade × magnitude do choque (top fatores)",
        x_label="Choque (%)",
        y_label="Elasticidade",
        lines=lines,
    )


def write_backtest_exceptions_chart(assets_dir: Path, run_id: str, backtest_rows: list[dict]) -> Path | None:
    """P&L realizado vs. limite da métrica (VaR_1dia) ao longo do tempo, com
    exceções marcadas — holding period 1 (uso canônico do semáforo, §Action
    08). Usa a `series` gravada em `backtest_results` por
    `_backtest_engine.backtest_for_holding_period` (índices reais do
    histórico congelado, nada recalculado aqui)."""
    h1_rows = [r for r in backtest_rows if r.get("holding_period") == 1 and r.get("series")]
    if not h1_rows:
        return None

    row = h1_rows[0]  # uma métrica por gráfico — evita sobrepor escalas de métricas diferentes
    series = row["series"]
    indices = series["indices"]
    realized_loss = series["realized_loss"]
    var_h = series["var_h"]
    exceedances = series["exceedances"]

    realized_points = list(zip((float(i) for i in indices), (float(v) for v in realized_loss)))
    var_points = list(zip((float(i) for i in indices), (float(v) for v in var_h)))
    marker_points = [(float(i), float(v)) for i, v, exc in zip(indices, realized_loss, exceedances) if exc]

    path = assets_dir / run_id / "backtest_exceptions.svg"
    return write_line_chart_svg(
        path,
        title=f"Backtest (h=1 dia) — {row['metrica']}: perda realizada vs. VaR",
        x_label="Índice no histórico congelado",
        y_label="Valor",
        lines={"perda realizada": realized_points, "VaR (limite)": var_points},
        markers=marker_points,
    )
