from __future__ import annotations

import logging
import sys
import threading
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import messagebox, ttk

from tkcalendar import DateEntry

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from promo_hedge_tool.config import Config, load_config, resolve_api_keys
from promo_hedge_tool.engine import execute
from promo_hedge_tool.event_selection import event_name, filter_events, local_event_time, local_timezone_label
from promo_hedge_tool.logging_config import configure_logging
from promo_hedge_tool.odds_client.client import OddsAPIClient
from promo_hedge_tool.odds_client.key_pool import KeyPool
from promo_hedge_tool.run_context import build_run_context, configured_bookmakers

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - only used when Pillow is unavailable
    Image = None
    ImageTk = None


logger = logging.getLogger(__name__)


class StableDateEntry(DateEntry):
    """Keep the calendar open while navigating its month controls."""

    def _on_focus_out_cal(self, event) -> None:
        self.after_idle(self._restore_calendar_focus_or_close)

    def _restore_calendar_focus_or_close(self) -> None:
        if not self._top_cal.winfo_ismapped():
            return

        pointer_x, pointer_y = self._top_cal.winfo_pointerxy()
        calendar_x = self._top_cal.winfo_rootx()
        calendar_y = self._top_cal.winfo_rooty()
        calendar_width = self._top_cal.winfo_width()
        calendar_height = self._top_cal.winfo_height()
        pointer_is_inside = (
            calendar_x <= pointer_x <= calendar_x + calendar_width
            and calendar_y <= pointer_y <= calendar_y + calendar_height
        )
        if pointer_is_inside:
            self._calendar.focus_force()
            return

        self._top_cal.withdraw()
        self.state(["!pressed"])


class BannerHeader(ttk.Frame):
    def __init__(self, parent: tk.Misc, config: Config):
        super().__init__(parent)
        self._image = None
        self._source_image = None
        project_root = Path(__file__).resolve().parent.parent
        image_path = Path(config.ui.banner_image)
        if not image_path.is_absolute():
            image_path = project_root / image_path

        self._label = ttk.Label(self, text="", anchor="center")
        self._label.pack(fill="x")
        if Image is None or ImageTk is None:
            self._label.configure(text="ArbFinder", padding=20)
            logger.warning("Pillow is unavailable; showing banner placeholder")
            return
        try:
            self._source_image = Image.open(image_path).convert("RGB")
            self.bind("<Configure>", self._render_banner)
            self.after_idle(self._render_banner)
        except (OSError, ValueError) as exc:
            self._label.configure(text="ArbFinder", padding=20)
            logger.warning("Unable to load banner %s: %s", image_path, exc)

    def _render_banner(self, _event=None) -> None:
        if self._source_image is None or ImageTk is None:
            return
        width = max(self.winfo_width(), 1)
        height = max(1, round(width * self._source_image.height / self._source_image.width))
        resized = self._source_image.resize(
            (width, height),
            Image.Resampling.LANCZOS,
        )
        self._image = ImageTk.PhotoImage(resized)
        self._label.configure(image=self._image)


class HedgeApp(tk.Tk):
    def __init__(self, config_path: str = "config/config.yaml"):
        super().__init__()
        self.title("ArbFinder")
        self.geometry("980x1100")
        self.minsize(900, 900)
        self.config_data = load_config(config_path)
        self.events: list[dict] = []
        self.event_by_index: dict[int, dict] = {}
        self.hedge_vars: dict[str, tk.BooleanVar] = {}

        BannerHeader(self, self.config_data).pack(fill="x")
        self._build_form()

    def _build_form(self) -> None:
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(11, weight=1)
        body.rowconfigure(15, weight=1)

        self.mode = tk.StringVar(value="profit-boost")
        self.base = tk.StringVar(value=configured_bookmakers(self.config_data)[0])
        boost_config = self.config_data.profit_boost
        default_stake = boost_config.get("default_stake") or "100"
        default_boost = boost_config.get("default_boost_percent") or "30"
        self.stake = tk.StringVar(value=str(default_stake))
        self.boost = tk.StringVar(value=str(default_boost))
        self.odds_operator = tk.StringVar(value="Any")
        self.odds_requirement = tk.StringVar(value="")
        self.league = tk.StringVar(value="All")
        self.keyword = tk.StringVar(value="")
        self.status = tk.StringVar(value="Set the query range, then click 'Find Events'.")

        default_start = datetime.now(timezone.utc).date()
        default_end = (datetime.now(timezone.utc) + timedelta(hours=self.config_data.event_window_hours)).date()
        start_date = StableDateEntry(body, date_pattern="mm/dd/yyyy", textvariable=tk.StringVar(), width=18)
        end_date = StableDateEntry(body, date_pattern="mm/dd/yyyy", textvariable=tk.StringVar(), width=18)
        start_date.set_date(default_start)
        end_date.set_date(default_end)
        self.from_date = start_date
        self.to_date = end_date

        fields = [
            ("Mode", ttk.Combobox(body, textvariable=self.mode, values=["bonus-bet", "profit-boost"], state="readonly")),
            ("Base bookmaker", ttk.Combobox(body, textvariable=self.base, values=configured_bookmakers(self.config_data), state="readonly")),
            ("Cash stake", ttk.Entry(body, textvariable=self.stake)),
            ("Boost percentage", ttk.Entry(body, textvariable=self.boost)),
            ("Base odds requirement", ttk.Combobox(body, textvariable=self.odds_operator, values=["Any", ">=", "<="], state="readonly")),
            ("American odds value", ttk.Entry(body, textvariable=self.odds_requirement)),
            ("League", ttk.Combobox(body, textvariable=self.league, values=["All"] + self._league_names(), state="readonly")),
            ("Start date (MM/DD/YYYY)", start_date),
            ("End date (MM/DD/YYYY)", end_date),
            ("Team keyword", ttk.Entry(body, textvariable=self.keyword)),
        ]
        for row, (title, widget) in enumerate(fields):
            ttk.Label(body, text=title).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            widget.grid(row=row, column=1, sticky="ew", pady=5)

        base_widget = fields[1][1]
        base_widget.bind("<<ComboboxSelected>>", lambda _event: self._refresh_hedge_selection())

        ttk.Label(body, text="Hedge bookmakers").grid(row=10, column=0, sticky="nw", padx=(0, 12), pady=5)
        hedge_frame = ttk.Frame(body)
        hedge_frame.grid(row=10, column=1, sticky="ew", pady=5)
        self.hedge_frame = hedge_frame
        self._refresh_hedge_selection()

        ttk.Label(body, text="Event selection").grid(row=11, column=0, sticky="nw", padx=(0, 12), pady=5)
        self.event_list = ttk.Treeview(body, columns=("event", "local_time"), show="headings", selectmode="browse", height=8)
        self.event_list.heading("event", text="Event")
        self.event_list.heading("local_time", text=f"Local start time ({local_timezone_label()})")
        self.event_list.column("event", anchor="w", width=360)
        self.event_list.column("local_time", anchor="w", width=220)
        self.event_list.grid(row=11, column=1, sticky="nsew", pady=5)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.event_list.yview)
        scrollbar.grid(row=11, column=2, sticky="ns", pady=5)
        self.event_list.configure(yscrollcommand=scrollbar.set)

        ttk.Label(body, textvariable=self.status).grid(row=12, column=0, columnspan=3, sticky="w", pady=(8, 4))
        actions = ttk.Frame(body)
        actions.grid(row=13, column=0, columnspan=3, sticky="e")
        ttk.Button(actions, text="Find Events", command=self.query_events).pack(side="left", padx=4)
        ttk.Button(actions, text="Run Analysis", command=self.run_analysis).pack(side="left", padx=4)

        ttk.Label(body, text="Top 3 results by locked profit").grid(row=14, column=0, sticky="nw", padx=(0, 12), pady=5)
        self.result_list = ttk.Treeview(
            body,
            columns=("event", "market", "base", "hedge", "profit"),
            show="headings",
            height=5,
        )
        result_headers = {
            "event": "Event",
            "market": "Market",
            "base": "Base",
            "hedge": "Hedge",
            "profit": "Locked profit",
        }
        for column, title in result_headers.items():
            self.result_list.heading(column, text=title)
        self.result_list.column("event", anchor="w", width=260, minwidth=220, stretch=False)
        self.result_list.column("market", anchor="w", width=100)
        self.result_list.column("base", anchor="w", width=110)
        self.result_list.column("hedge", anchor="w", width=110)
        self.result_list.column("profit", anchor="e", width=150, minwidth=140, stretch=False)
        self.result_list.grid(row=15, column=1, sticky="nsew", pady=5)
        self.result_list.bind("<Double-1>", self._show_selected_result)

    def _league_names(self) -> list[str]:
        names: list[str] = []
        for name, values in self.config_data.sports.items():
            if name == "soccer":
                names.extend(values.get("leagues", []))
            else:
                names.append(name)
        return names

    def _refresh_hedge_selection(self) -> None:
        available = [name for name in configured_bookmakers(self.config_data) if name != self.base.get()]
        for child in self.hedge_frame.winfo_children():
            child.destroy()
        self.hedge_vars = {}
        for name in available:
            selected = tk.BooleanVar(value=True)
            self.hedge_vars[name] = selected
            ttk.Checkbutton(self.hedge_frame, text=name, variable=selected).pack(anchor="w")

    def _sport_keys(self) -> list[str]:
        selected = self.league.get()
        keys: list[str] = []
        for name, values in self.config_data.sports.items():
            if name == "soccer":
                leagues = values.get("leagues", [])
                if selected == "All" or selected in leagues:
                    keys.extend(leagues if selected == "All" else [selected])
            elif selected == "All" or selected == name:
                if values.get("sport_key"):
                    keys.append(values["sport_key"])
        return list(dict.fromkeys(keys))

    def _query_window(self) -> tuple:
        start_date = self.from_date.get_date()
        end_date = self.to_date.get_date()
        if end_date < start_date:
            raise ValueError("End date must be on or after start date.")
        start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc).replace(microsecond=0)
        return start, end

    def query_events(self) -> None:
        try:
            commence_from, commence_to = self._query_window()
            api_keys = resolve_api_keys(self.config_data.odds_api.api_key_envs)
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("Query Parameter Error", str(exc))
            return

        self.status.set("Finding events...")
        threading.Thread(target=self._query_events_worker, args=(api_keys, commence_from, commence_to), daemon=True).start()

    def _query_events_worker(self, api_keys, commence_from, commence_to) -> None:
        try:
            client = OddsAPIClient(KeyPool(api_keys))
            events: list[dict] = []
            for sport_key in self._sport_keys():
                events.extend(client.get_events(
                    sport_key,
                    commenceTimeFrom=client._isoformat(commence_from),
                    commenceTimeTo=client._isoformat(commence_to),
                    dateFormat="iso",
                ))
            filtered = filter_events(events, self.keyword.get())
            self.after(0, self._show_events, filtered)
        except Exception as exc:  # pragma: no cover - network/UI boundary
            self.after(0, lambda: messagebox.showerror("Event Query Failed", str(exc)))
            self.after(0, lambda: self.status.set("Event query failed. Check the API key and query range."))

    def _show_events(self, events: list[dict]) -> None:
        self.events = events
        self.event_by_index = {}
        for item in self.event_list.get_children():
            self.event_list.delete(item)
        self.event_list.insert("", "end", iid="all", values=("All events", ""))
        for index, event in enumerate(events):
            item_id = str(index)
            self.event_by_index[index] = event
            self.event_list.insert("", "end", iid=item_id, values=(event_name(event), local_event_time(event)))
        self.event_list.selection_set("all")
        self.status.set(f"Found {len(events)} events. Select specific events or leave the list unselected to use the full range.")

    def run_analysis(self) -> None:
        try:
            stake = float(self.stake.get()) if self.mode.get() == "profit-boost" else None
            boost = float(self.boost.get()) if self.mode.get() == "profit-boost" else None
            odds_operator = None if self.mode.get() != "profit-boost" or self.odds_operator.get() == "Any" else self.odds_operator.get()
            odds_requirement = float(self.odds_requirement.get()) if odds_operator else None
            commence_from, commence_to = self._query_window()
            selected_items = self.event_list.selection()
            selected = () if not selected_items or selected_items[0] == "all" else (self.event_by_index[int(selected_items[0])]["id"],)
            selected_hedges = tuple(name for name, selected in self.hedge_vars.items() if selected.get())
            context = build_run_context(
                self.config_data,
                self.mode.get(),
                self.base.get(),
                stake=stake,
                boost_percent=boost,
                selected_leagues=tuple(self._sport_keys()),
                commence_time_from=commence_from,
                commence_time_to=commence_to,
                selected_event_ids=selected,
                team_keyword=self.keyword.get(),
                hedge_bookmakers=selected_hedges,
                odds_operator=odds_operator,
                odds_requirement_american=odds_requirement,
            )
            self.status.set("Fetching odds and calculating results...")
            threading.Thread(target=self._run_analysis_worker, args=(context,), daemon=True).start()
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Run Parameter Error", str(exc))

    def _run_analysis_worker(self, context) -> None:
        try:
            results = execute(self.config_data, context)
            top_results = sorted(results, key=lambda result: result.locked_profit, reverse=True)[:3]
            self.after(0, self._show_results, top_results)
            self.after(0, lambda: self.status.set(f"Analysis complete. Generated {len(results)} results in output."))
        except Exception as exc:  # pragma: no cover - network/UI boundary
            self.after(0, lambda: messagebox.showerror("Analysis Failed", str(exc)))
            self.after(0, lambda: self.status.set("Analysis failed. Check the platform data sources and API quota."))

    def _show_results(self, results) -> None:
        self.displayed_results = list(results)
        for item in self.result_list.get_children():
            self.result_list.delete(item)
        for index, result in enumerate(self.displayed_results):
            self.result_list.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    result.event_name,
                    result.market_key,
                    result.primary_bookmaker,
                    result.hedge_platform,
                    f"{result.locked_profit:.2f}",
                ),
            )

    def _show_selected_result(self, _event=None) -> None:
        selection = self.result_list.selection()
        if not selection:
            return
        result = self.displayed_results[int(selection[0])]
        details = tk.Toplevel(self)
        details.title(f"Bet details - {result.event_name}")
        details.geometry("620x430")
        details.transient(self)
        details.grab_set()

        body = ttk.Frame(details, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=result.event_name, font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(body, text=f"{result.sport_key} | {result.market_key} | {result.commence_time_local}").pack(anchor="w", pady=(4, 12))

        rows = [
            ("Base platform", result.primary_bookmaker),
            ("Base bet", result.primary_bet_description or result.primary_selection),
            ("Base odds", f"{result.primary_odds_decimal:.3f}"),
            ("Base stake", f"{result.primary_stake:.2f}"),
            ("Base potential return", f"{result.primary_return:.2f}"),
            ("Hedge platform", result.hedge_platform),
            ("Hedge bet", result.hedge_bet_description or result.hedge_selection),
            ("Hedge odds", f"{result.hedge_odds_decimal:.3f}"),
            ("Hedge stake", f"{result.hedge_stake:.2f}"),
            ("Hedge potential return", f"{result.hedge_return:.2f}"),
            ("Total cash staked", f"{result.total_cash_staked:.2f}"),
            ("Locked profit", f"{result.locked_profit:.2f}"),
            ("Conversion rate", f"{result.conversion_rate_pct:.2f}%"),
        ]
        table = ttk.Frame(body)
        table.pack(fill="x")
        for row, (label, value) in enumerate(rows):
            ttk.Label(table, text=label, width=24).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=2)
            ttk.Label(table, text=value).grid(row=row, column=1, sticky="w", pady=2)
        ttk.Button(body, text="Close", command=details.destroy).pack(anchor="e", pady=(16, 0))


def launch(config_path: str = "config/config.yaml") -> None:
    configure_logging()
    app = HedgeApp(config_path)
    app.mainloop()


if __name__ == "__main__":
    launch()