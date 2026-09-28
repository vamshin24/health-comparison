# GitHub Repository Health Comparison

A small Streamlit app for comparing the activity, popularity, and maintenance signals of two to four GitHub repositories.

## Requirements

- Python 3.10 or newer
- A network connection to `api.github.com`

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

The app opens in your browser. Enter repository names in `owner/name` form in the sidebar and select **Analyze**. The first two fields are prefilled with `langchain-ai/langchain` and `crewAIInc/crewAI`; the remaining fields are optional.

Public repositories work without authentication. GitHub allows 60 unauthenticated REST requests per hour per originating IP. To raise the limit, create a `.env` file in the project directory and add a personal access token:

```text
GITHUB_TOKEN=your_token_value
```

The token is read from the environment and is never displayed or logged. `.env` is excluded from Git.

## What the app retrieves

`data.py` retrieves repository metadata, language byte counts, weekly commit activity, up to 100 recent commits, and recently closed issues. Recent issue averages exclude pull requests and include issues closed in the last 90 days. GitHub's commit-activity statistics may return `202` while being calculated; the app retries three times and then shows a friendly notice if the data is still unavailable. API errors, rate-limit reset times, and network failures are shown in the app, and one failed repository does not hide successful comparisons.

`process.py` builds a weekly commit DataFrame with a four-week rolling average and calculates the comparison metrics. The 90-day commit total sums GitHub's weekly buckets whose week-start dates fall within the 90-day window; the boundary can therefore differ by part of a week. The issue-close median is based on recently closed issue records returned by GitHub, and is unavailable when there is no sample. Issues closed by bot accounts (for example, triage bots that auto-close issues within seconds) are excluded, since they would otherwise make close times look near-instant.

`app.py` renders metric cards, a weekly activity chart, a language mix chart, issue-close medians, and a generated commit-activity insight. API results are cached for one hour with Streamlit's data cache.

## Health score

The score is a simple 0–100 comparison signal, not a complete assessment of project quality:

- **Activity (0–40):** `min(commits_in_last_90_days / 90, 1) * 40`.
- **Issue response (0–30):** when a median close time exists, `max(0, 1 - min(median_days, 60) / 60) * 30`. If there is no recent closed-issue sample, the score assigns a neutral 15 points instead of treating missing data as poor maintenance.
- **Recency (0–30):** `max(0, 1 - days_since_last_push / 180) * 30`.

The components are added and rounded to the nearest whole point. Popularity metrics such as stars and forks are shown separately and do not affect the health score.

## GitHub API references

- [Repositories](https://docs.github.com/en/rest/repos/repos)
- [Repository statistics](https://docs.github.com/en/rest/metrics/statistics)
- [Commits](https://docs.github.com/en/rest/commits/commits)
- [Issues](https://docs.github.com/en/rest/issues/issues)
- [REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)