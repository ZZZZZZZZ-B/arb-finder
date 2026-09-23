# Promotion Hedge Arbitrage Tool

![Promotion Hedge Arbitrage Tool banner](config/background.jpg)

A Python tool for analyzing sports betting promotions with The Odds API. It supports Bonus Bet SNR and Profit Boost calculations, live event discovery, bookmaker selection, and two-sided hedge analysis.

## Features

- Select DraftKings, FanDuel, or another configured bookmaker as the base platform.
- Use all other configured platforms as hedge candidates.
- Calculate Bonus Bet SNR hedge opportunities.
- Calculate Profit Boost opportunities with a custom cash stake and boost percentage.
- Support Moneyline, Spread, and Totals binary markets.
- Filter by league, time window, event, or team keyword.
- Query live events and odds through The Odds API.
- Rotate across multiple API keys and skip exhausted keys.
- Rank the top 10 opportunities by conversion rate or locked profit.
- Export timestamped CSV and JSON result files.
- Open detailed bet instructions by double-clicking a result row.

## Requirements

- Python 3.10 or newer
- A The Odds API key
- Windows, macOS, or Linux

## Installation

Run these commands from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks virtual environment activation, use the interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## API Key Configuration

Provide one or more API keys through a single environment variable. Separate multiple keys with commas, semicolons, or newlines. Do not store keys in YAML files or Git:

```powershell
$env:ODDS_API_KEYS = "your-first-api-key,your-second-api-key"
```

The default configuration reads `ODDS_API_KEYS`:

```yaml
odds_api:
  api_key_envs: [ODDS_API_KEYS]
  key_rotation_strategy: round_robin
```

## Usage

### Graphical interface

Start the GUI with:

```powershell
python -m promo_hedge_tool
```

The interface lets you choose:

1. Bonus Bet or Profit Boost mode;
2. the base bookmaker;
3. the cash stake and boost percentage;
4. the league and time window;
5. specific events or a team keyword returned by the API.

After event selection, the tool retrieves odds, calculates hedge opportunities, and writes results to `output/`. Double-click a result to view the exact base and hedge selections, point values, odds, stakes, potential returns, total cash staked, locked profit, and conversion rate.

### Direct CLI

For a configuration-driven run without the GUI:

```powershell
python -m promo_hedge_tool.main
```

The CLI uses the sports, bookmakers, event window, and promotion settings from `config/config.yaml`.

## Configuration Files

- `config/config.yaml`: active application configuration for the GUI and CLI.
- `config/background.jpg`: GUI banner image.

The application reads `config/config.yaml` by default. Adjust `platforms`, `sports`, `promo`, and `odds_api.bookmakers` to match the bookmakers and sports available to your API account. Soccer requests use the API-supported `h2h` market and remove the `Draw` outcome locally.

## Output

Results are written to:

```text
output/hedge_results_<timestamp>.csv
output/hedge_results_<timestamp>.json
```

Results include the exact base and hedge selections, point values such as `Over 36.5`, odds, stakes, potential returns, total cash staked, locked profit, and conversion rate. In the GUI, double-click a result row to open the full bet details.

## Logging

The CLI and GUI write application logs to the project root:

```text
arb_finder.log
```

Log files and all generated files under `output/` are excluded from Git.

## Testing

```powershell
python -m pytest tests
```

The test suite covers:

- Bonus Bet SNR calculations;
- Profit Boost calculations, including negative-profit results;
- API key rotation;
- binary market filtering and matchup construction;
- dynamic base and hedge bookmaker roles;
- team keyword filtering and run-context validation.

## Notes and Limitations

- Available bookmakers and Soccer sport keys may vary by API account and season. Verify them against the live API response.
- A configured bookmaker without an Odds API source or external adapter may be listed but cannot provide odds at runtime.
- Available markets and bookmaker coverage depend on the API account and sport. The application logs API responses, quota headers, event counts, and quote counts to `arb_finder.log`.
- Profit Boost rules can vary by bookmaker. The current implementation uses one unified strict-locking model.
- This tool provides calculations only. It does not place bets or provide betting advice.
