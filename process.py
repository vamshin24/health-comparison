"""Transform raw GitHub repository data into comparison metrics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

import pandas as pd


def _utc_timestamp(value: str | None) -> pd.Timestamp | None:
    """Parse an ISO timestamp as UTC, returning None for absent or invalid values."""
    if not value:
        return None
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(timestamp) else timestamp


def _closed_by_bot(issue: Mapping[str, Any]) -> bool:
    """Return True when an automated account (e.g. a triage bot) closed the issue."""
    closer = issue.get("closed_by") or {}
    return closer.get("type") == "Bot" or str(closer.get("login", "")).endswith("[bot]")


def build_weekly_commits(repository_data: Mapping[str, Any]) -> pd.DataFrame:
    """Build weekly commit rows and a trailing four-week rolling average."""
    records = [
        {
            "week": pd.to_datetime(entry["week"], unit="s", utc=True),
            "commits": int(entry.get("total", 0)),
        }
        for entry in repository_data.get("weekly_activity", [])
        if "week" in entry
    ]
    frame = pd.DataFrame(records, columns=["week", "commits"])
    frame.insert(0, "repository", repository_data.get("full_name", "Repository"))
    if frame.empty:
        frame["rolling_average"] = pd.Series(dtype="float64")
        return frame
    frame = frame.sort_values("week").reset_index(drop=True)
    frame["rolling_average"] = frame["commits"].rolling(window=4, min_periods=1).mean()
    return frame


def calculate_metrics(repository_data: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate activity, issue-response, recency, popularity, and health metrics."""
    now = pd.Timestamp(datetime.now(timezone.utc))
    ninety_days_ago = now - pd.Timedelta(days=90)
    weekly_activity = repository_data.get("weekly_activity", [])
    commits_90d = sum(
        int(entry.get("total", 0))
        for entry in weekly_activity
        if (week := pd.to_datetime(entry.get("week", 0), unit="s", utc=True)) >= ninety_days_ago
    )

    close_durations: list[float] = []
    for issue in repository_data.get("recently_closed_issues", []):
        if _closed_by_bot(issue):
            continue
        created_at = _utc_timestamp(issue.get("created_at"))
        closed_at = _utc_timestamp(issue.get("closed_at"))
        if created_at is not None and closed_at is not None:
            close_durations.append(max(0.0, (closed_at - created_at).total_seconds() / 86400))
    median_close_days = float(pd.Series(close_durations).median()) if close_durations else None

    pushed_at = _utc_timestamp(repository_data.get("pushed_at"))
    days_since_push = (
        max(0.0, (now - pushed_at).total_seconds() / 86400) if pushed_at is not None else None
    )
    created_at = _utc_timestamp(repository_data.get("created_at"))
    age_years = (
        max((now - created_at).total_seconds() / (365.25 * 86400), 0.01)
        if created_at is not None
        else None
    )
    stars = int(repository_data.get("stars", 0))

    activity_score = min(commits_90d / 90, 1) * 40
    response_score = (
        15.0
        if median_close_days is None
        else max(0.0, 1 - min(median_close_days, 60) / 60) * 30
    )
    recency_score = (
        max(0.0, 1 - days_since_push / 180) * 30 if days_since_push is not None else 0.0
    )
    health_score = round(activity_score + response_score + recency_score)

    return {
        "commits_90d": commits_90d,
        "median_close_days": median_close_days,
        "days_since_push": days_since_push,
        "stars_per_year": stars / age_years if age_years else None,
        "health_score": health_score,
        "activity_score": round(activity_score, 1),
        "response_score": round(response_score, 1),
        "recency_score": round(recency_score, 1),
        "closed_issue_sample_size": len(close_durations),
    }


def process_repository(repository_data: Mapping[str, Any]) -> dict[str, Any]:
    """Combine normalized comparison metrics and weekly chart data for one repository."""
    return {
        "metrics": calculate_metrics(repository_data),
        "weekly_commits": build_weekly_commits(repository_data),
    }