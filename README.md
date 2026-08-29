# Daily AI News Digest

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/LLM-gpt--5--mini-412991?logo=openai&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/Scheduled-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

Collects AI news from 8 RSS sources, filters out duplicates and low-quality items, summarizes the top stories in Arabic via `gpt-5-mini`, and emails a formatted digest every morning through Gmail. Scheduled on GitHub Actions, so your machine doesn't need to be running.

## How it works

```
RSS sources  →  time-window filter + dedup + exclude previously sent
             →  pick the most important  →  fetch full text of selected articles  →  summarize in Arabic  →  HTML email
```

Each headline stays in English as a link to the original source, with a two-sentence Arabic summary underneath: what happened, and why it matters.

- **Fixed time window** — collects items published in the last 26 hours and shows up to 10 top stories with no minimum, so the digest may be shorter on quiet days.
- **No repeats** — sent links are saved to `state/seen.json`, excluded from future runs, and expire after `SEEN_RETENTION_DAYS` days. Updated only after a successful send, not in preview mode.
- **Automatic retry** — GitHub Actions retries at 8:17, 9:17, and 10:17 AM Riyadh time to work around scheduling delays. A marker in `state/last-digest.json` stops later attempts once one send succeeds, so you never get duplicates.
- **Full-article summaries** — a cheap first pass picks the top stories from titles/excerpts, then only those articles' full text is fetched (`trafilatura`) and summarized with full context, giving specific numbers and names instead of generic summaries. A failed fetch (paywall/blocking) just falls back to the RSS excerpt for that story.

## Sources

TechCrunch AI · The Verge AI · Ars Technica AI · Wired AI · OpenAI Blog · Google DeepMind · Hugging Face · MIT News AI

Edit the list via `FEEDS` in [config.py](config.py).

## Weekly projects report

On the Friday run (Riyadh time), the email also includes the top 5 AI-related GitHub repos created in the last 7 days (by stars), the top 3 trending Hugging Face items (one Model, one Dataset, one Space — preferring original weights over GGUF/MLX/FP8 variants, and skipping repeat model families), and the top 5 AI products from Product Hunt (by votes, Artificial Intelligence topic only). The model explains each item in Arabic; sent items are remembered to avoid repeats.

GitHub and Hugging Face fetching works without keys, but adding `GITHUB_TOKEN` and `HF_TOKEN` (locally in `.env`, and as GitHub Actions secrets) raises rate limits. Product Hunt requires a `PRODUCT_HUNT_TOKEN` from the [Product Hunt API Dashboard](https://www.producthunt.com/v2/oauth/applications). Day, counts, and lookback window are configurable via `WEEKLY_PROJECTS_*`, `GITHUB_PROJECT_COUNT`, `HUGGINGFACE_PROJECT_COUNT`, `PRODUCT_HUNT_COUNT`, and `PROJECT_LOOKBACK_DAYS` in [config.py](config.py).

## Setup

### 1. Gmail app password

Your regular Gmail password **will not work** — you need an App Password:

1. Enable 2-step verification at [myaccount.google.com/security](https://myaccount.google.com/security).
2. Open [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Create a new password named e.g. `News Automation`.
4. Copy the 16 characters, removing the spaces.

If the App Passwords page doesn't show up, 2-step verification is probably off, or it's a work/organization account where an admin blocks it.

### 2. OpenAI key

Get one from [platform.openai.com/api-keys](https://platform.openai.com/api-keys) and make sure the account has credit. Expected cost is under $1/month with `gpt-5-mini`.

### 3. Local test run

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `.env`, then preview without sending:

```powershell
.\.venv\Scripts\python.exe main.py --dry-run
```

This creates `preview.html` to open in your browser. If it looks good, send for real:

```powershell
.\.venv\Scripts\python.exe main.py
```

### 4. Scheduling on GitHub Actions

1. Create a **private** GitHub repo and push the project (`.env` is gitignored — double-check before pushing):

```powershell
git init
git add .
git commit -m "AI news daily digest automation"
git branch -M main
git remote add origin https://github.com/USERNAME/REPO.git
git push -u origin main
```

2. In `Settings → Secrets and variables → Actions`, add these repository secrets:

| Secret | Value |
| --- | --- |
| `GMAIL_USER` | Sender Gmail address |
| `GMAIL_APP_PASSWORD` | App password (16 characters) |
| `MAIL_TO` | Recipient email(s), comma-separated |
| `OPENAI_API_KEY` | OpenAI key |

3. From the `Actions` tab, select `AI News Digest → Run workflow` to test immediately.

The same log (per-stage token usage) is visible under `Actions → any run → Send digest`. To reduce reasoning-token usage, change `reasoning.effort` from `low` to `minimal` in [summarizer.py](summarizer.py).

## Send time

Default is 8:00 AM Riyadh time. To change it, edit `cron` in [.github/workflows/daily-news.yml](.github/workflows/daily-news.yml) — values are UTC (Riyadh time minus 3 hours):

| Riyadh time | cron value |
| --- | --- |
| 6:00 AM | `0 3 * * *` |
| 8:00 AM | `0 5 * * *` |
| 9:00 PM | `0 18 * * *` |

A 5-20 minute delay at peak times is normal GitHub Actions behavior, not an error.

## Other configurable settings

All in [config.py](config.py):

| Setting | Description | Default |
| --- | --- | --- |
| `LOOKBACK_HOURS` | Preferred time window, in hours | `26` |
| `MAX_ENTRIES_TO_MODEL` | Max number of stories sent to the model | `40` |
| `SEEN_RETENTION_DAYS` | How long sent stories are remembered | `30` |
| `MAX_ARTICLE_CHARS` | Max article text length sent to the model | `4000` |
| `OPENAI_MODEL` | Model used | `gpt-5-mini` |

## Troubleshooting

- **`Username and Password not accepted`** — using the regular Gmail password instead of an App Password, or leftover spaces in it.
- **Email has raw headlines with a warning banner** — the OpenAI call failed (bad key or no credit); check the log under `Actions`.
- **`No new unsent stories found`** — everything was already sent; normal on a quiet day. Delete the `state` folder to reset.
- **Duplicate stories despite memory** — GitHub Actions can evict its cache after 7 days idle or over the storage limit; it self-heals from the next run.
- **`Insufficient text from X, RSS excerpt will be used`** — the site blocked the fetch or is paywalled; not an error, that story just uses the RSS excerpt.
- **One source fails** — ignored, logged, and the rest of the digest continues.
- **Schedule stops firing** — GitHub disables schedules after 60 days of repo inactivity; any push or manual run reactivates it.
