# Promotion Hedge Analyzer

Analyze sportsbook promotions against odds from The Odds API. The desktop app supports Bonus Bet and Profit Boost calculations, event discovery, bookmaker selection, and two-sided hedge results.

## Features

- Bonus Bet SNR and Profit Boost calculations.
- Full-game moneyline, spread, and totals analysis.
- Configured period markets, including MLB first-inning run line and total runs.
- Event lookup by league and local date range, with optional team keyword filtering.
- Select a base bookmaker and one or more hedge bookmakers.
- Multi-key rotation and a persistent SQLite odds cache.
- CSV and JSON exports with bet selections, odds, stakes, returns, and profit details.

## Requirements

- Python 3.10 or newer
- A The Odds API key

## Install and Run

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:ODDS_API_KEYS = "your-first-api-key,your-second-api-key"
python -m promo_hedge_tool
```

On macOS or Linux, activate the environment with `source .venv/bin/activate` and set the key with `export ODDS_API_KEYS="your-api-key"`.

The application reads API keys from the environment variable named in `odds_api.api_key_envs`. Multiple keys may be separated by commas, semicolons, or newlines. Do not put API keys in configuration files or commit them to Git.

## Using the App

1. Choose Bonus Bet or Profit Boost, the base bookmaker, and the promotion values.
2. Select a league and local start/end dates. Optionally enter a team keyword.
3. Click **Find Events** and select one or more events. Leave events unselected for full-game analysis across the selected league and date range.
4. Choose hedge bookmakers. The `enabled` setting in the platform configuration determines which hedge options are checked by default.
5. Keep **Fetch latest Odds API data** checked to fetch odds and replace the local cache. Uncheck it to recalculate from cached odds without making odds requests.
6. Click **Run Analysis**. Double-click a result for its bet selections and stake details.

Period markets require selecting specific events and at least one market. The configured MLB first-inning markets are **Run Line** and **Total Runs**.

## Configuration

Edit `config/config.yaml` to configure sports, display titles, periods, bookmakers, and output settings.

- Sports use `sport_key` for a fixed league or `dynamic_prefix` for a group of event-specific keys. `title` controls the league name shown in the UI.
- Platforms use `title`, `enabled`, and `source`. For The Odds API platforms, set `source: odds_api`; use `bookmaker_key` when the API key differs from the platform name.
- `periods` maps UI market names and titles to The Odds API market keys.
- The Odds API bookmaker keys include regional variants. For example, PROLINE is `proline_ca_on`, Bet365 AU is `bet365_au`, and Hard Rock Bet is `hardrockbet`. Set the bookmaker key supported by your account and region.

Available sports, bookmakers, and markets depend on The Odds API coverage and subscription. Some bookmaker or sport combinations may return no odds. Bet365 AU currently has limited coverage and requires a paid subscription.

## Output and Cache

Results are saved under `output/`:

```text
hedge_results_<timestamp>.csv
hedge_results_<timestamp>.json
odds_cache.sqlite3
```

Fetching latest odds replaces the cached snapshot. Cached analysis reuses that snapshot and applies the current selections and promotion inputs.

## Tests

```powershell
python -m pytest -q
```

The tool performs calculations only; it does not place bets or provide betting advice.