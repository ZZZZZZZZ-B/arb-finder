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
from promo_hedge_tool.cost_estimator import (
    estimate_alt_market_cost_for_events,
    estimate_core_market_cost,
    estimate_run_cost,
    get_credit_thresholds,
)
from promo_hedge_tool.engine import execute, finalize_core_only, run_alt_phase, run_core_phase, select_prefilter_event_sports
from promo_hedge_tool.event_selection import event_name, filter_events, local_event_time, local_timezone_label
from promo_hedge_tool.logging_config import configure_logging
from promo_hedge_tool.odds_client.client import OddsAPIClient
from promo_hedge_tool.odds_client.key_pool import KeyPool
from promo_hedge_tool.odds_client.sport_key_resolver import SportKeyResolver
from promo_hedge_tool.run_context import build_run_context, configured_bookmakers
from promo_hedge_tool.odds_rules import decimal_to_american
from promo_hedge_tool.strategies.base import describe_market

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
        self.run_button: ttk.Button | None = None

        BannerHeader(self, self.config_data).pack(fill="x")
        self._build_form()

    def _build_form(self) -> None:
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, uniform="form_col")
        body.columnconfigure(1, weight=1, uniform="form_col")
        body.rowconfigure(3, weight=1)
        body.rowconfigure(6, weight=1)

        self.mode = tk.StringVar(value="profit-boost")
        self.period = tk.StringVar(value="full-game")
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
        self.fetch_latest = tk.BooleanVar(value=True)
        self.market_vars: dict[str, tk.BooleanVar] = {}
        self.status = tk.StringVar(value="Set the query range, then click 'Find Events'.")

        # Required fields on the left, optional fields on the right, side by side to use the full width.
        # Plain frames only -- purely a layout aid, no visible border or heading.
        required_frame = ttk.Frame(body)
        optional_frame = ttk.Frame(body)
        required_frame.grid(row=0, column=0, sticky="new", padx=(0, 8))
        optional_frame.grid(row=0, column=1, sticky="new", padx=(8, 0))
        required_frame.columnconfigure(1, weight=1)
        optional_frame.columnconfigure(1, weight=1)

        local_now = datetime.now().astimezone()
        default_start = local_now.date()
        default_end = (local_now + timedelta(hours=self.config_data.event_window_hours)).date()
        start_date = StableDateEntry(required_frame, date_pattern="mm/dd/yyyy", textvariable=tk.StringVar(), width=18)
        end_date = StableDateEntry(required_frame, date_pattern="mm/dd/yyyy", textvariable=tk.StringVar(), width=18)
        start_date.set_date(default_start)
        end_date.set_date(default_end)
        self.from_date = start_date
        self.to_date = end_date

        base_widget = ttk.Combobox(required_frame, textvariable=self.base, values=configured_bookmakers(self.config_data), state="readonly")
        self.league_widget = ttk.Combobox(optional_frame, textvariable=self.league, values=["All"] + self._league_names(), state="readonly")
        required_fields = [
            ("Mode *", ttk.Combobox(required_frame, textvariable=self.mode, values=["bonus-bet", "profit-boost", "no-sweat"], state="readonly")),
            ("Period *", ttk.Combobox(required_frame, textvariable=self.period, values=self._period_values(), state="readonly")),
            ("Base bookmaker *", base_widget),
            ("Cash stake / Bonus amount *", ttk.Entry(required_frame, textvariable=self.stake)),
            ("Boost percentage *", ttk.Entry(required_frame, textvariable=self.boost)),
            ("Start date *", start_date),
            ("End date *", end_date),
        ]
        optional_fields = [
            ("Base odds operator (optional)", ttk.Combobox(optional_frame, textvariable=self.odds_operator, values=["Any", ">=", "<="], state="readonly")),
            ("American odds value (optional)", ttk.Entry(optional_frame, textvariable=self.odds_requirement)),
            ("League (optional)", self.league_widget),
            ("Team keyword (optional)", ttk.Entry(optional_frame, textvariable=self.keyword)),
        ]
        for row, (title, widget) in enumerate(required_fields):
            ttk.Label(required_frame, text=title).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            widget.grid(row=row, column=1, sticky="ew", pady=5)
        for row, (title, widget) in enumerate(optional_fields):
            ttk.Label(optional_frame, text=title).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            widget.grid(row=row, column=1, sticky="ew", pady=5)

        base_widget.bind("<<ComboboxSelected>>", lambda _event: (self._refresh_hedge_selection(), self._refresh_run_button()))
        self.mode.trace_add("write", lambda *_args: self._on_mode_changed())
        self.period.trace_add("write", lambda *_args: self._on_period_changed())
        for variable in (self.base, self.stake, self.boost, self.odds_operator, self.odds_requirement):
            variable.trace_add("write", lambda *_args: self._refresh_run_button())

        ttk.Label(required_frame, text="Hedge bookmakers").grid(row=len(required_fields), column=0, sticky="nw", padx=(0, 12), pady=5)
        hedge_frame = ttk.Frame(required_frame)
        hedge_frame.grid(row=len(required_fields), column=1, sticky="ew", pady=5)
        self.hedge_frame = hedge_frame
        self._refresh_hedge_selection()

        ttk.Label(optional_frame, text="Alt Markets").grid(row=len(optional_fields), column=0, sticky="nw", padx=(0, 12), pady=5)
        self.market_frame = ttk.Frame(optional_frame)
        self.market_frame.grid(row=len(optional_fields), column=1, sticky="ew", pady=5)
        self._refresh_market_selection()

        ttk.Checkbutton(
            optional_frame,
            text="Fetch latest Odds API data",
            variable=self.fetch_latest,
        ).grid(row=len(optional_fields) + 1, column=0, columnspan=2, sticky="w", pady=5)

        ttk.Label(body, text="Event selection").grid(row=1, column=0, columnspan=2, sticky="nw", pady=(12, 0))
        event_frame = ttk.Frame(body)
        event_frame.grid(row=2, column=0, columnspan=2, sticky="nsew")
        event_frame.columnconfigure(0, weight=1)
        self.event_list = ttk.Treeview(event_frame, columns=("event", "local_time"), show="headings", selectmode="extended", height=8)
        self.event_list.heading("event", text="Event")
        self.event_list.heading("local_time", text=f"Local start time ({local_timezone_label()})")
        self.event_list.column("event", anchor="w", width=360)
        self.event_list.column("local_time", anchor="w", width=220)
        self.event_list.grid(row=0, column=0, sticky="nsew", pady=5)
        scrollbar = ttk.Scrollbar(event_frame, orient="vertical", command=self.event_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        self.event_list.configure(yscrollcommand=scrollbar.set)
        self.event_list.bind("<<TreeviewSelect>>", lambda _event: self._refresh_run_button())

        ttk.Label(body, textvariable=self.status).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))
        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(actions, text="Find Events", command=self.query_events).pack(side="left", padx=4)
        self.run_button = ttk.Button(actions, text="Run Analysis", command=self.run_analysis)
        self.run_button.pack(side="left", padx=4)

        ttk.Label(body, text="Top 10 results by locked profit").grid(row=5, column=0, columnspan=2, sticky="nw", pady=(12, 0))
        result_frame = ttk.Frame(body)
        result_frame.grid(row=6, column=0, columnspan=2, sticky="nsew")
        result_frame.columnconfigure(0, weight=1)
        self.result_list = ttk.Treeview(
            result_frame,
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
        self.result_list.grid(row=0, column=0, sticky="nsew", pady=5)
        result_scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.result_list.yview)
        result_scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        self.result_list.configure(yscrollcommand=result_scrollbar.set)
        self.result_list.bind("<Double-1>", self._show_selected_result)
        self._on_mode_changed()

    def _league_names(self) -> list[str]:
        names: list[str] = []
        for name, values in self.config_data.sports.items():
            if name == "soccer":
                names.extend(values.get("leagues", []))
            else:
                names.append(str(values.get("title", name)))
        return names

    def _selected_league_name(self, selection: str) -> str:
        if selection == "All":
            return selection
        for name, values in self.config_data.sports.items():
            if name == "soccer":
                if selection in values.get("leagues", []):
                    return selection
                continue
            if selection in {name, values.get("title"), values.get("sport_key")}:
                return name
        return selection

    def _period_values(self) -> list[str]:
        return ["full-game", *self.config_data.periods]

    def _refresh_market_selection(self) -> None:
        for child in self.market_frame.winfo_children():
            child.destroy()
        self.market_vars = {}
        if self.period.get() == "full-game":
            optional_markets = self.config_data.full_game_markets.get("optional_markets", {})
            for name, market in optional_markets.items():
                selected = tk.BooleanVar(value=False)
                self.market_vars[name] = selected
                ttk.Checkbutton(
                    self.market_frame,
                    text=market.get("title", name),
                    variable=selected,
                    command=self._refresh_run_button,
                ).pack(anchor="w")
            return
        definition = self.config_data.periods.get(self.period.get(), {})
        for name, market in definition.get("markets", {}).items():
            selected = tk.BooleanVar(value=True)
            self.market_vars[name] = selected
            ttk.Checkbutton(
                self.market_frame,
                text=market.get("title", name),
                variable=selected,
                command=self._refresh_run_button,
            ).pack(anchor="w")

    def _on_period_changed(self) -> None:
        if self.period.get() == "full-game":
            self.league_widget.configure(values=["All"] + self._league_names(), state="readonly")
            self.league.set("All")
        else:
            period_sports = self.config_data.periods.get(self.period.get(), {}).get("sport_keys", [])
            period_titles = [self._sport_display_title(sport_key) for sport_key in period_sports]
            self.league_widget.configure(values=period_titles, state="disabled")
            self.league.set(period_titles[0] if len(period_titles) == 1 else "All")
        self._refresh_market_selection()
        self._refresh_run_button()

    def _refresh_hedge_selection(self) -> None:
        available = [name for name in configured_bookmakers(self.config_data) if name != self.base.get()]
        for child in self.hedge_frame.winfo_children():
            child.destroy()
        self.hedge_vars = {}
        for name in available:
            platform_config = self.config_data.platforms.get(name, {})
            selected = tk.BooleanVar(value=bool(platform_config.get("enabled", False)))
            self.hedge_vars[name] = selected
            ttk.Checkbutton(
                self.hedge_frame,
                text=platform_config.get("title", name),
                variable=selected,
                command=self._refresh_run_button,
            ).pack(anchor="w")

    def _on_mode_changed(self) -> None:
        needs_boost = self.mode.get() == "profit-boost"
        self._set_field_state(self.boost, needs_boost)
        self._refresh_run_button()

    def _set_field_state(self, variable: tk.StringVar, enabled: bool) -> None:
        stack = list(self.winfo_children())
        while stack:
            widget = stack.pop()
            if isinstance(widget, ttk.Entry) and str(widget.cget("textvariable")) == str(variable):
                widget.configure(state="normal" if enabled else "disabled")
            stack.extend(widget.winfo_children())

    def _validate_form(self) -> str | None:
        if not self.base.get() or not self.mode.get():
            return "Mode and base bookmaker are required."
        if not any(selected.get() for selected in self.hedge_vars.values()):
            return "Select at least one hedge bookmaker."
        selected_items = self.event_list.selection()
        specific_items = tuple(item_id for item_id in selected_items if item_id != "all")
        if self.period.get() != "full-game":
            if not specific_items:
                return "Select at least one specific event for a period market."
            if not any(selected.get() for selected in self.market_vars.values()):
                return "Select at least one period market."
        try:
            amount = float(self.stake.get())
            if amount <= 0:
                return "Cash stake or bonus amount must be greater than zero."
            if self.mode.get() != "profit-boost":
                if self.odds_operator.get() != "Any":
                    float(self.odds_requirement.get())
            else:
                boost = float(self.boost.get())
                if boost < 0:
                    return "Boost percentage must not be negative."
                if self.odds_operator.get() != "Any":
                    float(self.odds_requirement.get())
            self._query_window()
        except (TypeError, ValueError):
            return "Complete all required numeric fields with valid values."
        return None

    def _refresh_run_button(self) -> None:
        if self.run_button is not None:
            self.run_button.configure(state="normal" if self._validate_form() is None else "disabled")

    def _sport_keys(self, resolver: SportKeyResolver | None = None) -> list[str]:
        if self.period.get() != "full-game":
            return list(self.config_data.periods.get(self.period.get(), {}).get("sport_keys", []))
        selected = self._selected_league_name(self.league.get())
        keys: list[str] = []
        for name, values in self.config_data.sports.items():
            if name == "soccer":
                leagues = values.get("leagues", [])
                if selected == "All" or selected in leagues:
                    keys.extend(leagues if selected == "All" else [selected])
            elif selected == "All" or selected == name:
                if values.get("sport_key"):
                    keys.append(values["sport_key"])
                elif values.get("dynamic_prefix"):
                    if resolver:
                        keys.extend(
                            resolver.resolve_dynamic_prefix(
                                values["dynamic_prefix"], include_inactive=True
                            )
                        )
                    else:
                        keys.append(name)
        return list(dict.fromkeys(keys))

    def _sport_display_title(self, sport_key: str) -> str:
        for values in self.config_data.sports.values():
            if values.get("sport_key") == sport_key:
                return str(values.get("title", sport_key))
            if values.get("dynamic_prefix") and sport_key.startswith(values["dynamic_prefix"]):
                return str(values.get("title", sport_key))
        return sport_key

    def _query_window(self) -> tuple:
        start_date = self.from_date.get_date()
        end_date = self.to_date.get_date()
        if end_date < start_date:
            raise ValueError("End date must be on or after start date.")
        start = datetime.combine(start_date, datetime.min.time()).astimezone(timezone.utc)
        end = datetime.combine(end_date, datetime.max.time()).astimezone(timezone.utc).replace(microsecond=0)
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
            resolver = SportKeyResolver(client)
            events: list[dict] = []
            for sport_key in self._sport_keys(resolver):
                sport_events = client.get_events(
                    sport_key,
                    commenceTimeFrom=client._isoformat(commence_from),
                    commenceTimeTo=client._isoformat(commence_to),
                    dateFormat="iso",
                )
                sport_title = self._sport_display_title(sport_key)
                events.extend(
                    {
                        **event,
                        "sport_key": sport_key,
                        "display_sport_title": sport_title,
                    }
                    for event in sport_events
                )
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
            sport_title = event.get("display_sport_title") or event.get("sport_title") or event.get("sport_key", "")
            display_name = f"{sport_title} | {event_name(event)}" if sport_title else event_name(event)
            self.event_list.insert("", "end", iid=item_id, values=(display_name, local_event_time(event)))
        self.status.set(f"Found {len(events)} events. Select specific events or leave the list unselected to use the full range.")

    def run_analysis(self) -> None:
        try:
            validation_error = self._validate_form()
            if validation_error:
                raise ValueError(validation_error)
            stake = float(self.stake.get()) if self.mode.get() in {"profit-boost", "no-sweat"} else None
            bonus_amount = float(self.stake.get()) if self.mode.get() == "bonus-bet" else None
            boost = float(self.boost.get()) if self.mode.get() == "profit-boost" else None
            odds_operator = None if self.odds_operator.get() == "Any" else self.odds_operator.get()
            odds_requirement = float(self.odds_requirement.get()) if odds_operator else None
            commence_from, commence_to = self._query_window()
            selected_items = self.event_list.selection()
            specific_items = tuple(item_id for item_id in selected_items if item_id != "all")
            selected = tuple(self.event_by_index[int(item_id)]["id"] for item_id in specific_items)
            selected_event_sports = tuple(
                dict.fromkeys(
                    (
                        self.event_by_index[int(item_id)].get("sport_key", ""),
                        self.event_by_index[int(item_id)]["id"],
                    )
                    for item_id in specific_items
                    if self.event_by_index[int(item_id)].get("sport_key")
                )
            )
            selected_leagues = tuple(self._sport_keys())
            if specific_items:
                selected_leagues = tuple(
                    dict.fromkeys(
                        self.event_by_index[int(item_id)].get("sport_key", "")
                        for item_id in specific_items
                        if self.event_by_index[int(item_id)].get("sport_key")
                    )
                )
            selected_markets = tuple(name for name, selected in self.market_vars.items() if selected.get())
            selected_hedges = tuple(name for name, selected in self.hedge_vars.items() if selected.get())
            context = build_run_context(
                self.config_data,
                self.mode.get(),
                self.base.get(),
                stake=stake,
                bonus_amount=bonus_amount,
                boost_percent=boost,
                selected_leagues=selected_leagues,
                selected_event_sports=selected_event_sports,
                commence_time_from=commence_from,
                commence_time_to=commence_to,
                selected_event_ids=selected,
                team_keyword=self.keyword.get(),
                hedge_bookmakers=selected_hedges,
                odds_operator=odds_operator,
                odds_requirement_american=odds_requirement,
                period=self.period.get(),
                selected_markets=selected_markets,
            )
            if not self.fetch_latest.get():
                self._launch_analysis(context, False)
                return
            if self.period.get() == "full-game" and selected_markets and not specific_items:
                self.status.set("Estimating core market API credit usage...")
                threading.Thread(target=self._estimate_core_cost_worker, args=(context,), daemon=True).start()
                return
            self.status.set("Estimating API credit usage...")
            threading.Thread(target=self._estimate_cost_worker, args=(context,), daemon=True).start()
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Run Parameter Error", str(exc))

    def _estimate_cost_worker(self, context) -> None:
        try:
            api_keys = resolve_api_keys(self.config_data.odds_api.api_key_envs)
            client = OddsAPIClient(KeyPool(api_keys))
            estimate = estimate_run_cost(self.config_data, context, client)
            self.after(0, self._handle_cost_estimate, context, estimate)
        except Exception as exc:  # pragma: no cover - network/UI boundary
            self.after(0, lambda: messagebox.showerror("Cost Estimate Failed", str(exc)))
            self.after(0, lambda: self.status.set("Cost estimate failed. Check the API key and query range."))

    def _handle_cost_estimate(self, context, estimate) -> None:
        _, alt_threshold = get_credit_thresholds(self.config_data)
        if estimate.total <= alt_threshold:
            self._launch_analysis(context, True)
            return
        self._show_cost_confirmation(context, estimate)

    def _show_cost_confirmation(self, context, estimate) -> None:
        self.status.set(f"Estimated usage is {estimate.total} API credits. Awaiting confirmation.")
        self._build_confirmation_dialog(
            title="Confirm API Credit Usage",
            headline=f"This run is estimated to use approximately {estimate.total} API credits.",
            lines=estimate.lines,
            on_confirm=lambda: self._launch_analysis(context, True),
            on_cancel=lambda: self.status.set("Run cancelled before using API credits."),
        )

    def _build_confirmation_dialog(self, title: str, headline: str, lines: list[str], on_confirm, on_cancel) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=headline, font=("TkDefaultFont", 10, "bold"), wraplength=420).pack(anchor="w", pady=(0, 8))
        for line in lines:
            ttk.Label(body, text=f"- {line}", wraplength=420).pack(anchor="w")
        ttk.Label(body, text="Continue with this API call?", wraplength=420).pack(anchor="w", pady=(8, 0))
        actions = ttk.Frame(body)
        actions.pack(anchor="e", pady=(12, 0))

        def confirm() -> None:
            dialog.destroy()
            on_confirm()

        def cancel() -> None:
            dialog.destroy()
            on_cancel()

        ttk.Button(actions, text="Cancel", command=cancel).pack(side="left", padx=4)
        ttk.Button(actions, text="Confirm", command=confirm).pack(side="left", padx=4)
        dialog.protocol("WM_DELETE_WINDOW", cancel)

    def _launch_analysis(self, context, fetch_latest: bool) -> None:
        self.status.set("Fetching odds and calculating results...")
        threading.Thread(target=self._run_analysis_worker, args=(context, fetch_latest), daemon=True).start()

    def _run_analysis_worker(self, context, fetch_latest: bool) -> None:
        try:
            results = execute(self.config_data, context, fetch_latest=fetch_latest)
            self.after(0, self._handle_final_results, results)
        except Exception as exc:  # pragma: no cover - network/UI boundary
            self.after(0, lambda: messagebox.showerror("Analysis Failed", str(exc)))
            self.after(0, lambda: self.status.set("Analysis failed. Check the platform data sources and API quota."))

    # -- Two-stage flow: core full-game markets first, then a prefiltered alt-market pass --

    def _estimate_core_cost_worker(self, context) -> None:
        try:
            api_keys = resolve_api_keys(self.config_data.odds_api.api_key_envs)
            client = OddsAPIClient(KeyPool(api_keys))
            estimate = estimate_core_market_cost(self.config_data, context, client)
            self.after(0, self._handle_core_cost_estimate, context, estimate)
        except Exception as exc:  # pragma: no cover - network/UI boundary
            self.after(0, lambda: messagebox.showerror("Cost Estimate Failed", str(exc)))
            self.after(0, lambda: self.status.set("Cost estimate failed. Check the API key and query range."))

    def _handle_core_cost_estimate(self, context, estimate) -> None:
        core_threshold, _ = get_credit_thresholds(self.config_data)
        if estimate.total <= core_threshold:
            self._launch_core_phase(context)
            return
        self._show_core_cost_confirmation(context, estimate)

    def _show_core_cost_confirmation(self, context, estimate) -> None:
        self.status.set(f"Estimated core market usage is {estimate.total} API credits. Awaiting confirmation.")
        self._build_confirmation_dialog(
            title="Confirm Core Market API Usage",
            headline=f"The core market query is estimated to use approximately {estimate.total} API credits.",
            lines=estimate.lines,
            on_confirm=lambda: self._launch_core_phase(context),
            on_cancel=lambda: self.status.set("Run cancelled before using API credits."),
        )

    def _launch_core_phase(self, context) -> None:
        self.status.set("Fetching core market odds...")
        threading.Thread(target=self._run_core_phase_worker, args=(context,), daemon=True).start()

    def _run_core_phase_worker(self, context) -> None:
        try:
            core_phase = run_core_phase(self.config_data, context)
            self.after(0, self._after_core_phase, context, core_phase)
        except Exception as exc:  # pragma: no cover - network/UI boundary
            self.after(0, lambda: messagebox.showerror("Analysis Failed", str(exc)))
            self.after(0, lambda: self.status.set("Analysis failed. Check the platform data sources and API quota."))

    def _after_core_phase(self, context, core_phase) -> None:
        event_sports = select_prefilter_event_sports(self.config_data, context, core_phase.core_results)
        if not event_sports:
            self.status.set("No profitable core-market events found; alternate markets skipped.")
            self._launch_core_only_finalize(context, core_phase)
            return
        estimate = estimate_alt_market_cost_for_events(self.config_data, context, event_sports)
        _, alt_threshold = get_credit_thresholds(self.config_data)
        if estimate.total <= alt_threshold:
            self._launch_alt_phase(context, core_phase, event_sports)
            return
        self._show_alt_cost_confirmation(context, core_phase, event_sports, estimate)

    def _show_alt_cost_confirmation(self, context, core_phase, event_sports, estimate) -> None:
        self.status.set(f"Estimated alternate market usage is {estimate.total} API credits. Awaiting confirmation.")
        self._build_confirmation_dialog(
            title="Confirm Alternate Market API Usage",
            headline=(
                f"The alternate market query on {len(event_sports)} profitable event(s) is estimated to use "
                f"approximately {estimate.total} API credits."
            ),
            lines=estimate.lines,
            on_confirm=lambda: self._launch_alt_phase(context, core_phase, event_sports),
            on_cancel=lambda: self._launch_core_only_finalize(context, core_phase),
        )

    def _launch_alt_phase(self, context, core_phase, event_sports) -> None:
        self.status.set("Fetching alternate market odds...")
        threading.Thread(target=self._run_alt_phase_worker, args=(context, core_phase, event_sports), daemon=True).start()

    def _run_alt_phase_worker(self, context, core_phase, event_sports) -> None:
        try:
            results = run_alt_phase(self.config_data, context, core_phase, event_sports)
            self.after(0, self._handle_final_results, results)
        except Exception as exc:  # pragma: no cover - network/UI boundary
            self.after(0, lambda: messagebox.showerror("Analysis Failed", str(exc)))
            self.after(0, lambda: self.status.set("Analysis failed. Check the platform data sources and API quota."))

    def _launch_core_only_finalize(self, context, core_phase) -> None:
        threading.Thread(target=self._finalize_core_only_worker, args=(context, core_phase), daemon=True).start()

    def _finalize_core_only_worker(self, context, core_phase) -> None:
        try:
            results = finalize_core_only(self.config_data, context, core_phase)
            self.after(0, self._handle_final_results, results)
        except Exception as exc:  # pragma: no cover - network/UI boundary
            self.after(0, lambda: messagebox.showerror("Analysis Failed", str(exc)))
            self.after(0, lambda: self.status.set("Analysis failed. Check the platform data sources and API quota."))

    def _handle_final_results(self, results) -> None:
        top_results = sorted(results, key=lambda result: result.locked_profit, reverse=True)[:10]
        self._show_results(top_results)
        self.status.set(f"Analysis complete. Generated {len(results)} results in output.")

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
                    describe_market(result.market_key),
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
        ttk.Label(body, text=f"{result.sport_key} | {describe_market(result.market_key)} | {result.commence_time_local}").pack(anchor="w", pady=(4, 12))

        rows = [
            ("Base platform", result.primary_bookmaker),
            ("Base bet", result.primary_bet_description or result.primary_selection),
            ("Base odds", f"{result.primary_odds_decimal:.3f}"),
            ("Base American odds", f"{decimal_to_american(result.primary_odds_decimal):+.0f}"),
            ("Base stake", f"{result.primary_stake:.2f}"),
            ("Base potential return", f"{result.primary_return:.2f}"),
            ("Hedge platform", result.hedge_platform),
            ("Hedge bet", result.hedge_bet_description or result.hedge_selection),
            ("Hedge odds", f"{result.hedge_odds_decimal:.3f}"),
            ("Hedge American odds", f"{decimal_to_american(result.hedge_odds_decimal):+.0f}"),
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