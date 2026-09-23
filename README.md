# Promotion Hedge Arbitrage Tool

![Promotion Hedge Arbitrage Tool banner](config/background.jpg)

A Python tool for analyzing sports betting promotions with The Odds API. It supports Bonus Bet SNR and Profit Boost calculations, live event discovery, bookmaker selection, and two-sided hedge analysis.

## Features

- Select DraftKings, FanDuel, or another configured bookmaker as the base platform.
- Use all other configured platforms as hedge candidates.
- Calculate Bonus Bet SNR hedge opportunities.
- Calculate Profit Boost opportunities with a custom cash stake and boost percentage.
- Support Moneyline, Draw No Bet, Spread, and Totals binary markets.
- Filter by league, time window, event, or team keyword.
- Query live events and odds through The Odds API.
- Rotate across multiple API keys and skip exhausted keys.
- Rank the top 10 opportunities by conversion rate or locked profit.
- Export timestamped CSV and JSON result files.
- Display `config/background.jpg` as the GUI banner.

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

Provide API keys through environment variables. Do not store keys in YAML files or Git:

```powershell
$env:ODDS_API_KEY = "your-api-key"
```

Multiple keys are supported:

```powershell
$env:ODDS_API_KEY_1 = "your-first-api-key"
$env:ODDS_API_KEY_2 = "your-second-api-key"
```

Configure the environment variable names in YAML:

```yaml
odds_api:
  api_key_envs: [ODDS_API_KEY_1, ODDS_API_KEY_2]
  key_rotation_strategy: round_robin
```

## Usage

### Graphical interface

Start the phase-two GUI with:

```powershell
python -m promo_hedge_tool
```

The interface lets you choose:

1. Bonus Bet or Profit Boost mode;
2. the base bookmaker;
3. the cash stake and boost percentage;
4. the league and time window;
5. specific events or a team keyword returned by the API.

After event selection, the tool retrieves odds, calculates hedge opportunities, and writes results to `output/`.

## Configuration Files

- `config/config.yaml`: active application configuration for the GUI and CLI.
- `config/background.jpg`: GUI banner image.

The phase-two GUI reads `config/config.yaml` by default. Adjust `platforms`, `sports`, and `odds_api.bookmakers` to match the bookmakers and sports available to your API account.

## Output

Results are written to:

```text
output/hedge_results_<timestamp>.csv
output/hedge_results_<timestamp>.json
```

Results include event, market, base bookmaker, hedge bookmaker, odds, hedge stake, locked profit, and conversion rate. JSON output also includes the run mode, filters, and bookmaker configuration snapshot.

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

## Project Structure

```text
arb-finder/
├── config/
│   ├── config.yaml
│   └── background.jpg
├── promo_hedge_tool/
│   ├── odds_client/              # The Odds API client and key rotation
│   ├── strategies/               # Bonus Bet and Profit Boost strategies
│   ├── engine.py                 # Query, matchup, calculation, and export flow
│   ├── event_selection.py        # Event and team filtering
│   ├── run_context.py            # Parameters for one run
│   ├── ui.py                     # Tkinter graphical interface
│   └── main.py                   # Legacy CLI entry point
├── tests/
├── output/
├── requirements.txt
└── README.md
```

## Design Documents

The local product requirements, technical design, and phase-two extension design documents remain excluded through `.git/info/exclude`.

## Notes and Limitations

- Available bookmakers and Soccer sport keys may vary by API account and season. Verify them against the live API response.
- A configured bookmaker without an Odds API source or external adapter may be listed but cannot provide odds at runtime.
- Profit Boost rules can vary by bookmaker. The current implementation uses one unified strict-locking model.
- This tool provides calculations only. It does not place bets or provide betting advice.
