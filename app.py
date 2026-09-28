"""Streamlit interface for comparing GitHub repository health."""

from __future__ import annotations

import html
from typing import Any, Callable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data import GitHubAPIError, fetch_repository_data
from process import process_repository

# Series colors, one per repository slot. Validated (lightness, chroma, colorblind
# separation, contrast) against the dark surface below; assigned in input order.
SERIES_COLORS = ["#9d7cf0", "#23a894", "#c4851c", "#d0558a"]
SURFACE = "#0f1419"
INK = "#e6edf3"
MUTED = "#8b98a5"
GRID = "#222a33"
ACCENT = "#5cc8ff"

PAGE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500;700&display=swap');
:root { --surface:#0f1419; --raised:#161c24; --line:#26303b; --ink:#e6edf3; --muted:#8b98a5; --accent:#5cc8ff; }
html, body, .stApp, [class*="css"] { font-family:'IBM Plex Sans', sans-serif; }
.stApp { background:var(--surface); color:var(--ink); }
.block-container { padding-top:4.2rem; padding-bottom:3rem; max-width:1280px; }
button[kind="primaryFormSubmit"], button[kind="primary"] { color:#0f1419 !important; font-weight:600; }
button[kind="primaryFormSubmit"] p, button[kind="primary"] p { color:#0f1419 !important; }
section[data-testid="stSidebar"] { background:var(--raised); border-right:1px solid var(--line); }
h1, h2, h3, h4 { color:var(--ink); letter-spacing:0; }
.mono { font-family:'JetBrains Mono', monospace; }
.hero-kicker { font-family:'JetBrains Mono', monospace; color:var(--accent); font-size:.8rem; letter-spacing:.12em; text-transform:uppercase; }
.hero-title { font-family:'JetBrains Mono', monospace; font-size:2.1rem; font-weight:700; color:var(--ink); margin:.2rem 0 .3rem; }
.hero-sub { color:var(--muted); margin-bottom:1.4rem; }
.insight { border-left:3px solid var(--accent); background:linear-gradient(90deg, rgba(92,200,255,.10), transparent 70%); padding:14px 18px; border-radius:0 8px 8px 0; font-size:1.15rem; color:var(--ink); margin:0 0 1.6rem; }
.insight b { font-family:'JetBrains Mono', monospace; color:var(--accent); }
.section-label { font-family:'JetBrains Mono', monospace; color:var(--muted); font-size:.75rem; letter-spacing:.14em; text-transform:uppercase; margin:1.8rem 0 .6rem; border-bottom:1px solid var(--line); padding-bottom:.4rem; }
.lb-row { display:grid; grid-template-columns:56px minmax(0,1fr) 300px; gap:18px; align-items:center; padding:14px 18px; border:1px solid var(--line); border-radius:10px; background:var(--raised); margin-bottom:10px; }
.lb-rank { font-family:'JetBrains Mono', monospace; font-size:1.5rem; font-weight:700; color:var(--muted); }
.lb-row.first .lb-rank { color:var(--accent); }
.lb-name { font-size:1.1rem; font-weight:600; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.lb-name a { color:var(--ink) !important; text-decoration:none; }
.lb-name a:hover { text-decoration:underline; }
.dot { width:11px; height:11px; border-radius:50%; display:inline-block; flex:none; }
.chip { font-family:'JetBrains Mono', monospace; font-size:.7rem; color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:1px 8px; }
.lb-stats { color:var(--muted); font-size:.88rem; margin-top:4px; }
.lb-stats span { color:var(--ink); font-family:'JetBrains Mono', monospace; }
.lb-score { display:grid; grid-template-columns:auto 1fr; gap:4px 14px; align-items:center; }
.lb-num { font-family:'JetBrains Mono', monospace; font-size:2.2rem; font-weight:700; color:var(--ink); line-height:1; grid-row:span 2; }
.lb-num small { font-size:.8rem; color:var(--muted); font-weight:500; }
.lb-bar { display:flex; gap:2px; height:8px; background:var(--line); border-radius:4px; overflow:hidden; }
.lb-bar .seg { background:var(--accent); height:100%; }
.lb-legend { font-size:.74rem; color:var(--muted); font-family:'JetBrains Mono', monospace; }
.h2h { width:100%; border-collapse:collapse; font-size:.92rem; }
.h2h th, .h2h td { padding:9px 12px; border-bottom:1px solid var(--line); text-align:right; }
.h2h th:first-child, .h2h td:first-child { text-align:left; color:var(--muted); }
.h2h th { font-weight:600; color:var(--ink); }
.h2h td { font-family:'JetBrains Mono', monospace; color:var(--ink); }
.h2h td:first-child { font-family:'IBM Plex Sans', sans-serif; }
.h2h td.win { color:var(--accent); font-weight:700; }
.h2h td.win::after { content:" ▲"; font-size:.7em; }
.formula { background:var(--raised); border:1px solid var(--line); border-radius:10px; padding:16px 18px; color:var(--ink); font-size:.9rem; }
.formula code { color:var(--accent); background:transparent; font-size:.82rem; }
.formula p { color:var(--muted); margin:.4rem 0 0; }
@media (max-width: 760px) {
  .lb-row { grid-template-columns:40px minmax(0,1fr); }
  .lb-score { grid-column:1 / -1; }
  .hero-title { font-size:1.5rem; }
}
</style>
"""


def _load_comparison(repository_names: list[str]) -> list[dict[str, Any]]:
    """Fetch and process each repository independently, retaining errors for the UI."""
    results: list[dict[str, Any]] = []
    for repository_name in repository_names:
        if not repository_name:
            continue
        try:
            raw_data = fetch_repository_data(repository_name)
            results.append(
                {
                    "requested_name": repository_name,
                    "data": raw_data,
                    "processed": process_repository(raw_data),
                    "error": None,
                }
            )
        except GitHubAPIError as error:
            results.append(
                {
                    "requested_name": repository_name,
                    "data": None,
                    "processed": None,
                    "error": error,
                }
            )
    return results


def _color_map(results: list[dict[str, Any]]) -> dict[str, str]:
    """Assign each repository a fixed series color by its input order."""
    return {
        result["data"]["full_name"]: SERIES_COLORS[index % len(SERIES_COLORS)]
        for index, result in enumerate(results)
    }


def _style_figure(figure: go.Figure, height: int) -> go.Figure:
    """Apply the shared dark, low-chrome chart styling to a Plotly figure."""
    figure.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "IBM Plex Sans, sans-serif", "color": INK, "size": 12},
        margin={"l": 8, "r": 16, "t": 36, "b": 8},
        barcornerradius=4,
        hoverlabel={"bgcolor": "#1c2430", "bordercolor": GRID, "font": {"color": INK}},
        showlegend=False,
    )
    figure.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, tickfont={"color": MUTED})
    figure.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, tickfont={"color": MUTED})
    figure.update_annotations(font={"color": INK, "size": 13})
    return figure


def _leaderboard_html(results: list[dict[str, Any]], colors: dict[str, str]) -> str:
    """Build ranked leaderboard rows: identity, headline stats, and health score split."""
    ranked = sorted(results, key=lambda result: result["processed"]["metrics"]["health_score"], reverse=True)
    rows: list[str] = []
    for rank, result in enumerate(ranked, start=1):
        data = result["data"]
        metrics = result["processed"]["metrics"]
        name = html.escape(data["full_name"])
        url = html.escape(data["html_url"], quote=True)
        segments = "".join(
            f'<div class="seg" style="width:{value}%;opacity:{opacity}" title="{label}: {value:g}"></div>'
            for label, value, opacity in (
                ("Activity", metrics["activity_score"], 1.0),
                ("Issue response", metrics["response_score"], 0.7),
                ("Recency", metrics["recency_score"], 0.45),
            )
        )
        rows.append(
            f'<div class="lb-row{" first" if rank == 1 else ""}">'
            f'<div class="lb-rank">#{rank}</div>'
            f'<div><div class="lb-name"><span class="dot" style="background:{colors[data["full_name"]]}"></span>'
            f'<a href="{url}" target="_blank">{name}</a><span class="chip">{html.escape(str(data["license"]))}</span></div>'
            f'<div class="lb-stats">★ <span>{data["stars"]:,}</span> stars &nbsp;·&nbsp; '
            f'⑂ <span>{data["forks"]:,}</span> forks &nbsp;·&nbsp; '
            f'◎ <span>{data["open_issues"]:,}</span> open issues</div></div>'
            f'<div class="lb-score"><div class="lb-num">{metrics["health_score"]}<small>/100</small></div>'
            f'<div class="lb-bar">{segments}</div>'
            f'<div class="lb-legend">act {metrics["activity_score"]:g}/40 · issues {metrics["response_score"]:g}/30 · '
            f'recency {metrics["recency_score"]:g}/30</div></div>'
            "</div>"
        )
    return "".join(rows)


def _head_to_head_html(results: list[dict[str, Any]], colors: dict[str, str]) -> str:
    """Build a metric-by-repository table that highlights the best value in each row."""
    Row = tuple[str, Callable[[dict[str, Any]], Any], Callable[[Any], str], str | None]
    rows: list[Row] = [
        ("Commits, last 90 days", lambda r: r["processed"]["metrics"]["commits_90d"], lambda v: f"{v:,}", "high"),
        ("Median days to close an issue", lambda r: r["processed"]["metrics"]["median_close_days"], lambda v: f"{v:.1f}", "low"),
        ("Days since last push", lambda r: r["processed"]["metrics"]["days_since_push"], lambda v: f"{v:.0f}", "low"),
        ("Stars per year of age", lambda r: r["processed"]["metrics"]["stars_per_year"], lambda v: f"{v:,.0f}", "high"),
        ("Watchers", lambda r: r["data"]["watchers"], lambda v: f"{v:,}", "high"),
        ("Closed-issue sample size", lambda r: r["processed"]["metrics"]["closed_issue_sample_size"], lambda v: f"{v:,}", None),
    ]
    header = "".join(
        f'<th><span class="dot" style="background:{colors[r["data"]["full_name"]]}"></span> '
        f'{html.escape(r["data"]["full_name"])}</th>'
        for r in results
    )
    body: list[str] = []
    for label, getter, formatter, better in rows:
        values = [getter(result) for result in results]
        present = [value for value in values if value is not None]
        best = None
        if better and len(present) > 1 and len(set(present)) > 1:
            best = max(present) if better == "high" else min(present)
        cells = "".join(
            f'<td class="{"win" if value is not None and value == best else ""}">'
            f'{formatter(value) if value is not None else "—"}</td>'
            for value in values
        )
        body.append(f"<tr><td>{label}</td>{cells}</tr>")
    return f'<table class="h2h"><thead><tr><th>Metric</th>{header}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def _weekly_commit_chart(results: list[dict[str, Any]], colors: dict[str, str]) -> go.Figure:
    """Create one panel per repository: weekly commit bars with a 4-week rolling average line."""
    names = [result["data"]["full_name"] for result in results]
    figure = make_subplots(rows=len(results), cols=1, shared_xaxes=True, vertical_spacing=0.09, subplot_titles=names)
    for row, result in enumerate(results, start=1):
        frame = result["processed"]["weekly_commits"]
        name = result["data"]["full_name"]
        if frame.empty:
            continue
        figure.add_trace(
            go.Bar(
                x=frame["week"],
                y=frame["commits"],
                marker={"color": colors[name], "opacity": 0.35},
                hovertemplate="Week of %{x|%b %d, %Y}<br>%{y} commits<extra>" + html.escape(name) + "</extra>",
            ),
            row=row,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=frame["week"],
                y=frame["rolling_average"],
                mode="lines",
                line={"color": colors[name], "width": 2},
                hovertemplate="4-week average: %{y:.1f}<extra>" + html.escape(name) + "</extra>",
            ),
            row=row,
            col=1,
        )
    figure.update_yaxes(matches="y", title_text=None)
    figure.update_layout(bargap=0.15)
    figure.update_annotations(xanchor="left", x=0)
    return _style_figure(figure, height=150 * len(results) + 60)


def _language_chart(results: list[dict[str, Any]], colors: dict[str, str]) -> go.Figure:
    """Create side-by-side panels of each repository's top five languages by byte share."""
    names = [result["data"]["full_name"] for result in results]
    figure = make_subplots(rows=1, cols=len(results), subplot_titles=names, horizontal_spacing=0.08)
    for column, result in enumerate(results, start=1):
        languages = result["data"]["languages"]
        total = sum(languages.values())
        name = result["data"]["full_name"]
        if not total:
            continue
        ordered = sorted(languages.items(), key=lambda item: item[1], reverse=True)
        top = [(language, count / total * 100) for language, count in ordered[:5]]
        other = sum(count for _, count in ordered[5:]) / total * 100
        if other >= 0.5:
            top.append(("Other", other))
        figure.add_trace(
            go.Bar(
                x=[share for _, share in top],
                y=[language for language, _ in top],
                orientation="h",
                marker={"color": colors[name]},
                text=[f"{share:.0f}%" if share >= 1 else "<1%" for _, share in top],
                textposition="outside",
                textfont={"color": INK},
                cliponaxis=False,
                hovertemplate="%{y}: %{x:.1f}% of bytes<extra>" + html.escape(name) + "</extra>",
            ),
            row=1,
            col=column,
        )
    figure.update_xaxes(visible=False, range=[0, 118])
    figure.update_yaxes(autorange="reversed", showgrid=False)
    figure.update_layout(bargap=0.3)
    for index, annotation in enumerate(figure.layout.annotations):
        annotation.update(xanchor="left", x=figure.layout[f"xaxis{index + 1 if index else ''}"].domain[0])
    return _style_figure(figure, height=300)


def _issue_close_chart(results: list[dict[str, Any]], colors: dict[str, str]) -> go.Figure:
    """Create a horizontal bar chart of median issue close time, fastest first."""
    ordered = sorted(
        results,
        key=lambda r: (r["processed"]["metrics"]["median_close_days"] is None, r["processed"]["metrics"]["median_close_days"] or 0),
    )
    names = [r["data"]["full_name"] for r in ordered]
    medians = [r["processed"]["metrics"]["median_close_days"] for r in ordered]
    samples = [r["processed"]["metrics"]["closed_issue_sample_size"] for r in ordered]
    figure = go.Figure(
        go.Bar(
            x=[value or 0 for value in medians],
            y=names,
            orientation="h",
            marker={"color": [colors[name] for name in names]},
            text=[f"{value:.1f} days" if value is not None else "no recent sample" for value in medians],
            textposition="outside",
            textfont={"color": INK},
            cliponaxis=False,
            customdata=samples,
            hovertemplate="%{y}<br>Median %{x:.1f} days · %{customdata} closed issues<extra></extra>",
        )
    )
    longest = max((value for value in medians if value is not None), default=1) or 1
    figure.update_xaxes(title_text="Median days from open to close (last 90 days)", range=[0, longest * 1.35], title_font={"color": MUTED})
    figure.update_yaxes(autorange="reversed", showgrid=False)
    figure.update_layout(bargap=0.4)
    return _style_figure(figure, height=90 * len(results) + 90)


def _generate_insight(results: list[dict[str, Any]]) -> str:
    """Summarize the strongest 90-day commit activity comparison from fetched data."""
    ranked = sorted(
        results,
        key=lambda result: result["processed"]["metrics"]["commits_90d"],
        reverse=True,
    )
    leader = ranked[0]
    leader_count = leader["processed"]["metrics"]["commits_90d"]
    if len(ranked) < 2:
        return f"{leader['data']['full_name']} recorded {leader_count:,} commits in the last 90 days."
    runner_up = ranked[1]
    runner_count = runner_up["processed"]["metrics"]["commits_90d"]
    if leader_count == runner_count:
        return f"{leader['data']['full_name']} and {runner_up['data']['full_name']} are level at {leader_count:,} commits in the last 90 days."
    if runner_count == 0:
        return f"{leader['data']['full_name']} recorded {leader_count:,} commits in the last 90 days; {runner_up['data']['full_name']} recorded none."
    ratio = leader_count / runner_count
    return (
        f"{leader['data']['full_name']} had {ratio:.1f}x more commits than "
        f"{runner_up['data']['full_name']} in the last 90 days "
        f"({leader_count:,} vs {runner_count:,})."
    )


def _section(label: str) -> None:
    """Render a small monospace section divider label."""
    st.markdown(f'<div class="section-label">{html.escape(label)}</div>', unsafe_allow_html=True)


def main() -> None:
    """Render the repository comparison inputs, leaderboard, charts, and health-score guide."""
    st.set_page_config(page_title="Repo Health", layout="wide")
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-kicker">github · repository health</div>'
        '<div class="hero-title">repo/health — compare</div>'
        '<div class="hero-sub">Activity, issue response, and recency, scored from GitHub’s public REST API.</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown('<div class="hero-kicker">Repositories</div>', unsafe_allow_html=True)
        with st.form("repository_comparison"):
            repository_fields = [
                st.text_input("Repository 1", value="langchain-ai/langchain", placeholder="owner/name"),
                st.text_input("Repository 2", value="crewAIInc/crewAI", placeholder="owner/name"),
                st.text_input("Repository 3", placeholder="owner/name (optional)"),
                st.text_input("Repository 4", placeholder="owner/name (optional)"),
            ]
            submitted = st.form_submit_button("Analyze", type="primary", width="stretch")
        st.caption("Enter 2–4 repositories as owner/name. Results are cached for an hour.")

    if submitted:
        selected_names = [name.strip() for name in repository_fields if name.strip()]
        if not 2 <= len(selected_names) <= 4:
            st.session_state["comparison_results"] = []
            st.session_state["comparison_input_error"] = "Enter between two and four repositories."
        elif len({name.casefold() for name in selected_names}) != len(selected_names):
            st.session_state["comparison_results"] = []
            st.session_state["comparison_input_error"] = "Each repository must be unique."
        else:
            st.session_state["comparison_input_error"] = None
            with st.spinner("Fetching repository data from GitHub..."):
                st.session_state["comparison_results"] = _load_comparison(selected_names)

    input_error = st.session_state.get("comparison_input_error")
    if input_error:
        st.error(input_error)

    results = st.session_state.get("comparison_results", [])
    successful = [result for result in results if result["error"] is None]
    failed = [result for result in results if result["error"] is not None]
    for result in failed:
        st.error(f"{result['requested_name']}: {result['error']}")

    if not results:
        st.info("Enter two to four repositories in the sidebar and press Analyze.")
        return
    if not successful:
        st.warning("No repository data was available to compare.")
        return

    colors = _color_map(successful)
    insight = html.escape(_generate_insight(successful))
    st.markdown(f'<div class="insight"><b>Insight →</b> {insight}</div>', unsafe_allow_html=True)
    for result in successful:
        if result["data"]["activity_message"]:
            st.info(f"{result['data']['full_name']}: {result['data']['activity_message']}")

    _section("Leaderboard · ranked by health score")
    st.markdown(_leaderboard_html(successful, colors), unsafe_allow_html=True)

    if len(successful) < 2:
        st.info("A comparison needs at least two successfully retrieved repositories.")
        return

    _section("Head to head")
    st.markdown(_head_to_head_html(successful, colors), unsafe_allow_html=True)

    _section("Weekly commits · bars = weekly total, line = 4-week average")
    st.plotly_chart(_weekly_commit_chart(successful, colors), width="stretch")
    for result in successful:
        if not result["data"]["activity_message"] and result["processed"]["weekly_commits"].empty:
            st.caption(f"{result['data']['full_name']}: no weekly activity history was returned.")

    _section("Languages · top five by share of code bytes")
    st.plotly_chart(_language_chart(successful, colors), width="stretch")

    _section("Issue resolution & scoring")
    issue_column, formula_column = st.columns([3, 2], gap="large")
    with issue_column:
        st.plotly_chart(_issue_close_chart(successful, colors), width="stretch")
    with formula_column:
        st.markdown(
            '<div class="formula"><b>How the health score works (0–100)</b>'
            "<p><code>activity = min(commits_90d / 90, 1) × 40</code><br>"
            "Full 40 points at 90+ commits in the last 90 days.</p>"
            "<p><code>issues = max(0, 1 − min(median_days, 60) / 60) × 30</code><br>"
            "30 for same-day closes, 0 at 60+ days. Bot-closed issues are excluded; "
            "no recent sample earns a neutral 15.</p>"
            "<p><code>recency = max(0, 1 − days_since_push / 180) × 30</code><br>"
            "30 for a push today, 0 after 180 days.</p>"
            "<p>The three parts are summed and rounded. Stars and forks are shown but don’t affect the score. "
            "90-day commit totals use GitHub’s weekly buckets, so the window edge can shift by part of a week.</p>"
            "</div>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
