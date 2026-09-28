"""Retrieve repository health data from the GitHub REST API."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
import streamlit as st
from dotenv import load_dotenv

API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
REQUEST_TIMEOUT = 20
STATISTICS_RETRIES = 3


class GitHubAPIError(Exception):
    """Represent a user-actionable GitHub API failure."""

    def __init__(self, message: str, category: str, reset_at: int | None = None) -> None:
        """Store a displayable message, failure category, and optional reset time."""
        super().__init__(message)
        self.category = category
        self.reset_at = reset_at


def _request_json(url: str, params: dict[str, Any] | None = None) -> Any:
    """Send one authenticated-or-anonymous GET and translate common API failures."""
    load_dotenv()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as error:
        raise GitHubAPIError(
            "Could not reach GitHub. Check your network connection and try again.",
            "network",
        ) from error

    if response.status_code in (403, 429):
        remaining = response.headers.get("X-RateLimit-Remaining")
        if response.status_code == 429 or remaining == "0":
            reset_at = response.headers.get("X-RateLimit-Reset")
            try:
                reset_epoch = int(reset_at) if reset_at else None
            except ValueError:
                reset_epoch = None
            message = "GitHub API rate limit reached."
            if reset_epoch:
                reset_time = datetime.fromtimestamp(reset_epoch, timezone.utc)
                message += f" It resets at {reset_time:%Y-%m-%d %H:%M:%S} UTC."
            raise GitHubAPIError(message, "rate_limit", reset_epoch)

    if response.status_code == 404:
        raise GitHubAPIError(
            "Repository not found or not publicly accessible. Check the owner/name spelling.",
            "not_found",
        )

    if not response.ok and response.status_code != 202:
        detail = ""
        try:
            detail = response.json().get("message", "")
        except (ValueError, AttributeError):
            pass
        raise GitHubAPIError(
            f"GitHub returned HTTP {response.status_code}"
            + (f": {detail}" if detail else "."),
            "api_error",
        )

    if response.status_code == 204:
        return None
    if response.status_code == 202:
        return None
    try:
        return response.json()
    except ValueError as error:
        raise GitHubAPIError("GitHub returned an unreadable response.", "api_error") from error


def _fetch_commit_activity(owner: str, repository: str) -> tuple[list[dict[str, int]], str | None]:
    """Fetch weekly commit activity, retrying while GitHub computes the statistics."""
    url = f"{API_ROOT}/repos/{owner}/{repository}/stats/commit_activity"
    for attempt in range(STATISTICS_RETRIES):
        result = _request_json(url)
        if result is not None:
            return result, None
        if attempt < STATISTICS_RETRIES - 1:
            time.sleep(1.5)
    return [], "GitHub is still preparing weekly activity data. Try again shortly."


def _fetch_recent_commits(owner: str, repository: str, since: datetime) -> list[dict[str, Any]]:
    """Fetch up to 100 commits from the last 90 days for recent-activity context."""
    result = _request_json(
        f"{API_ROOT}/repos/{owner}/{repository}/commits",
        {"since": since.isoformat().replace("+00:00", "Z"), "per_page": 100},
    )
    return result or []


def _fetch_recently_closed_issues(
    owner: str, repository: str, since: datetime
) -> list[dict[str, Any]]:
    """Fetch recently updated closed issues and retain only issues closed in the window."""
    since_iso = since.isoformat().replace("+00:00", "Z")
    url = f"{API_ROOT}/repos/{owner}/{repository}/issues"
    closed_issues: list[dict[str, Any]] = []
    page = 1
    while page <= 10:
        result = _request_json(
            url,
            {
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "since": since_iso,
                "per_page": 100,
                "page": page,
            },
        )
        items = result or []
        if not items:
            break
        for issue in items:
            if issue.get("pull_request") or not issue.get("closed_at"):
                continue
            closed_at = datetime.fromisoformat(issue["closed_at"].replace("Z", "+00:00"))
            if closed_at >= since:
                closed_issues.append(issue)
        if len(items) < 100:
            break
        page += 1
    return closed_issues


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_repository_data(repository_name: str) -> dict[str, Any]:
    """Retrieve and cache the metadata and activity for one owner/name repository."""
    normalized_name = repository_name.strip()
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", normalized_name):
        raise GitHubAPIError("Enter a repository as owner/name.", "invalid_input")
    owner, repository = normalized_name.split("/", maxsplit=1)
    repo_url = f"{API_ROOT}/repos/{owner}/{repository}"
    metadata = _request_json(repo_url)

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=90)
    activity, activity_message = _fetch_commit_activity(owner, repository)
    languages = _request_json(f"{repo_url}/languages") or {}
    recent_commits = _fetch_recent_commits(owner, repository, since)
    recently_closed_issues = _fetch_recently_closed_issues(owner, repository, since)

    license_info = metadata.get("license") or {}
    return {
        "full_name": metadata.get("full_name", normalized_name),
        "html_url": metadata.get("html_url", ""),
        "stars": metadata.get("stargazers_count", 0),
        "forks": metadata.get("forks_count", 0),
        "open_issues": metadata.get("open_issues_count", 0),
        "watchers": metadata.get("subscribers_count", metadata.get("watchers_count", 0)),
        "license": license_info.get("spdx_id") or license_info.get("name") or "No license",
        "created_at": metadata.get("created_at"),
        "pushed_at": metadata.get("pushed_at"),
        "languages": languages,
        "weekly_activity": activity,
        "activity_message": activity_message,
        "recent_commits": recent_commits,
        "recently_closed_issues": recently_closed_issues,
        "fetched_at": now.isoformat(),
    }