import pandas as pd
import streamlit as st

from db.queries import (
    get_matches_df, get_snapshots_df,
    get_opening_odds, get_closing_odds, get_line_changes_df,
)
from config import MARKETS_AVAILABLE
from pages.utils import highlight_pivot, sport_label_map, to_local_str

st.title("Vývoj kurzů")
st.caption("Tabulkový přehled pohybu kurzů v čase pro vybraný zápas a trh.")

df_all = get_matches_df()

if df_all.empty:
    st.info("Žádné zápasy. Přejdi na **Matches** a fetchni kurzy.")
    st.stop()

labels = sport_label_map(df_all)

# ── Filtry ────────────────────────────────────────────────────────────────────
with st.container(border=True):
    fc0, fc1, fc2, fc3 = st.columns([2, 3, 2, 3])
    with fc0:
        available_sports = sorted(labels.keys())
        sport_filter = st.multiselect(
            "Soutěž", available_sports,
            format_func=lambda k: labels.get(k, k),
            placeholder="Všechny",
        )
    df_matches = df_all[df_all["sport_key"].isin(sport_filter)] if sport_filter else df_all
    if df_matches.empty:
        st.info("Žádné zápasy pro vybranou soutěž.")
        st.stop()
    df_matches = df_matches.copy()
    df_matches["label"] = df_matches["home_team"] + " vs " + df_matches["away_team"]

    with fc1:
        idx = st.selectbox(
            "Zápas",
            range(len(df_matches)),
            format_func=lambda i: df_matches["label"].iloc[i],
        )
        match_id = df_matches["id"].iloc[idx]
    with fc2:
        df_snap = get_snapshots_df(match_id)
        if df_snap.empty:
            st.info("Pro tento zápas nejsou žádné snapshoty.")
            st.stop()
        market = st.selectbox(
            "Trh",
            df_snap["market"].unique().tolist(),
            format_func=lambda k: MARKETS_AVAILABLE.get(k, k),
        )
    with fc3:
        books_all = df_snap[df_snap["market"] == market]["bookmaker"].unique().tolist()
        default_books = ["pinnacle"] if "pinnacle" in books_all else books_all[:1]
        selected_books = st.multiselect("Bookmakeři", books_all, default=default_books)

filtered = df_snap[
    (df_snap["market"] == market) &
    (df_snap["bookmaker"].isin(selected_books))
].copy()

if filtered.empty:
    st.info("Žádná data pro tento filtr.")
    st.stop()

# ── Pivot tabulka: čas × bookmaker·výběr ──────────────────────────────────────
st.markdown("### Kurzy v čase")

filtered["col"] = filtered["bookmaker"] + " · " + filtered["selection"]
if filtered["line"].notna().any():
    filtered["col"] = filtered["col"] + " @" + filtered["line"].apply(
        lambda x: str(x) if x is not None else ""
    )

filtered["čas"] = to_local_str(filtered["snapshot_time"])
_tz_label = "Čas (Praha)"

pivot = filtered.pivot_table(
    index="čas", columns="col", values="odds", aggfunc="first"
)
pivot.index.name   = _tz_label
pivot.columns.name = ""

st.dataframe(
    pivot.style.apply(highlight_pivot, axis=None).format("{:.2f}", na_rep="—"),
    use_container_width=True,
)
st.caption("🟢 Kurz vzrostl &nbsp;|&nbsp; 🔴 Kurz klesl &nbsp;|&nbsp; Každý řádek = jeden snapshot")

# ── Opening vs Closing ────────────────────────────────────────────────────────
st.markdown("### Opening vs Closing kurzy")

df_open  = get_opening_odds(match_id, market)
df_close = get_closing_odds(match_id, market)

if not df_open.empty and not df_close.empty:
    merged = df_open.merge(
        df_close,
        on=["bookmaker", "market", "selection", "line"],
        suffixes=("_open", "_close"),
    )
    merged["Pohyb"] = (merged["odds_close"] - merged["odds_open"]).round(3)
    merged["Pohyb str"] = merged["Pohyb"].apply(
        lambda x: f"+{x:.2f}" if x > 0 else f"{x:.2f}"
    )
    display = merged[["bookmaker", "selection", "line",
                       "odds_open", "odds_close", "Pohyb str"]].copy()
    display.columns = ["Bookmaker", "Výběr", "Linie", "Opening", "Closing", "Pohyb"]

    def _color_pohyb(val: str) -> str:
        if str(val).startswith("+"):
            return "color:#4caf50;font-weight:bold"
        if str(val).startswith("-"):
            return "color:#ef5350;font-weight:bold"
        return ""

    st.dataframe(
        display.style
            .map(_color_pohyb, subset=["Pohyb"])
            .format({"Opening": "{:.2f}", "Closing": "{:.2f}"}, na_rep="—"),
        use_container_width=True, hide_index=True,
    )
    st.caption("Opening = první zaznamenaný kurz · Closing = poslední kurz před výkopem")
elif not df_open.empty:
    st.info("Closing kurzy nejsou k dispozici — potřebné jsou snapshoty pořízené před výkopem zápasu.")
else:
    st.info("Žádné snapshoty pro tuto kombinaci.")

# ── Detekované změny ──────────────────────────────────────────────────────────
df_lc = get_line_changes_df(match_id)
if not df_lc.empty:
    df_lc = df_lc[df_lc["market"] == market]

if not df_lc.empty:
    st.markdown("### Detekované změny")

    display_lc = df_lc[[
        "detected_at", "bookmaker", "selection",
        "old_line", "new_line", "old_odds", "new_odds",
        "odds_delta", "minutes_to_kickoff",
    ]].copy()
    display_lc["detected_at"] = to_local_str(display_lc["detected_at"])
    display_lc["minutes_to_kickoff"] = display_lc["minutes_to_kickoff"].apply(
        lambda x: f"{int(x)} min" if x is not None else "—"
    )
    display_lc.columns = [
        "Čas", "Bookmaker", "Výběr",
        "Stará linie", "Nová linie", "Starý kurz", "Nový kurz",
        "Δ kurz", "Do KO",
    ]

    def _color_delta(val) -> str:
        try:
            return "color:#4caf50" if float(val) > 0 else "color:#ef5350"
        except Exception:
            return ""

    st.dataframe(
        display_lc.style
            .map(_color_delta, subset=["Δ kurz"])
            .format({"Starý kurz": "{:.2f}", "Nový kurz": "{:.2f}", "Δ kurz": "{:+.2f}"}, na_rep="—"),
        use_container_width=True, hide_index=True,
    )
