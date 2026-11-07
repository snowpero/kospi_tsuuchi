# KOSPI Telegram Alert Bot (GitHub Actions)

## Features
- `/upper 4200`: set upper threshold
- `/lower 3700`: set lower threshold
- `/status`: show settings
- `/price`: latest available KOSPI price (may be delayed)
- `/on` and `/off`: enable/disable threshold notifications
- `/help`: show commands
- Alerts repeat on each scheduled run during KOSPI regular market hours when price is outside thresholds.
- Commands are processed 24/7 when the workflow runs, including weekends.

## Setup
1. Upload `main.py`, `requirements.txt`, `state.json`, and `.github/workflows/kospi-alert.yml` to the **root** of your existing GitHub repository, replacing old files. Remove the earlier test-message workflow step if you added it.
2. Under **Settings > Secrets and variables > Actions**, keep these repository secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Under **Settings > Actions > General**, allow workflows and ensure **Workflow permissions** allow read/write if repository policy requires it. This workflow declares `permissions: contents: write`.
4. Ensure the default branch is not protected against pushes by GitHub Actions. State is saved by committing `state.json` back to the repository. A branch ruleset blocking pushes will prevent settings persistence.
5. Run **Actions > KOSPI Telegram Alert > Run workflow**. Send `/status` to your bot and manually run again to check that it replies.
6. Send `/upper 4200`, then manually run again. You should receive confirmation; check that `state.json` was updated in the repository.

## How it works
- GitHub Actions cron: every five minutes, 24 hours a day. Scheduled runs may be delayed or skipped; this is not a real-time bot.
- Reads Telegram messages with `getUpdates` and processes commands from `TELEGRAM_CHAT_ID` only.
- Stores upper/lower/enabled/update_offset in `state.json`, committed by the workflow for persistence.
- Checks KOSPI thresholds only on weekdays from 09:00 to 15:30 KST. Exchange holidays are not separately recognized, but stale quote checking prevents stale alerts.
- `/price` may return the last quote outside market hours.

## Notes and limitations
- The bot must not have a Telegram webhook configured, as `getUpdates` does not work while a webhook is active. For a bot used only with this project, remove a webhook via `https://api.telegram.org/bot<TOKEN>/deleteWebhook` (never share your token).
- If you have used the bot before, queued updates may be processed on first run (up to 100 per run). Avoid sending unrelated commands from other chats.
- Only the configured chat ID can control this bot. Keep your GitHub secrets private.
- The workflow commits changes to `state.json` when commands are processed. If branch protection blocks the push, subsequent runs may repeat replies. Resolve permissions before relying on the bot.
- A failed command reply can be repeated on retry; there is no transactional guarantee between Telegram delivery and GitHub commits.
- Yahoo Finance data is unofficial and may be delayed, rate-limited, or unavailable. This is not suitable for time-critical trading.
- Frequent 24/7 runs may consume GitHub Actions minutes on private repositories. Public repositories generally have free standard-hosted runner usage, subject to GitHub policies.
- If the repo's default branch is not `main`, GitHub still schedules workflows on the default branch.
- GitHub may disable scheduled workflows on inactive public repositories after prolonged inactivity.
