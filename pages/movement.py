import pandas as pd
import streamlit as st

from db.queries import (
    get_matches_df, get_snapshots_df,
    get_opening_odds, get_closing_odds, get_line_changes_df,
)
from config import MARKETS_AVAILABLE
from pages.utils import highlight_pivot, sport_label_map, to_local_str

st.title("Vývoj kurzů")
st.caption("Pinnacle — pohyb kurzů v čase pro vybraný zápas a trh.")

df_all = get_matches_df()

if df_all.empty:
    st.info("Žádné zápasy. Přejdi na **Matches** a fetchni kurzy.")
    st.stop()

labels = sport_label_map(df_all)

# ── Filtry ────────────────────────────────────────────────────────────────────
with st.container(border=True):
    fc0, fc1, fc2 = st.columns([2, 3, 2])
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

filtered_all = df_snap[
    (df_snap["market"] == market) &
    (df_snap["bookmaker"] == "pinnacle")
].copy()

match_info = df_all[df_all["id"] == match_id].iloc[0]
commence_time = match_info["commence_time"]

filtered = filtered_all[filtered_all["snapshot_time"] <= commence_time]
post_kickoff_count = len(filtered_all) - len(filtered)

if filtered.empty:
    st.info("Pro tento zápas a trh nejsou žádné pre-kickoff Pinnacle snapshoty.")
    st.stop()

available_lines = sorted(filtered["line"].dropna().unique().tolist())
if available_lines:
    selected_line = st.selectbox(
        "Linie", available_lines,
        format_func=lambda x: f"{x:g}",
        key="mov_line",
    )
    filtered = filtered[filtered["line"] == selected_line]

# ── Pivot tabulka: čas × bookmaker·výběr ──────────────────────────────────────
st.markdown("### Kurzy v čase")

filtered["col"] = filtered["selection"]

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
ko_str = commence_time[:16].replace("T", " ")
caption = f"🟢 Kurz vzrostl &nbsp;|&nbsp; 🔴 Kurz klesl &nbsp;|&nbsp; Poslední řádek = Closing · Výkop: {ko_str} UTC"
if post_kickoff_count > 0:
    caption += f" &nbsp;|&nbsp; ⚠️ {post_kickoff_count} post-kickoff snapshot(ů) skryto — live kurzy nejsou relevantní pro analýzu"
st.caption(caption)

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
    merged["čas_open"]  = to_local_str(merged["snapshot_time_open"])
    merged["čas_close"] = to_local_str(merged["snapshot_time_close"])
    display = merged[["bookmaker", "selection", "line",
                       "čas_open", "odds_open",
                       "čas_close", "odds_close", "Pohyb str"]].copy()
    display.columns = ["Bookmaker", "Výběr", "Linie",
                       "Čas Opening", "Opening",
                       "Čas Closing", "Closing", "Pohyb"]

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
    st.caption("Closing = poslední fetch PŘED výkopem (ne poslední řádek v pivotu — ten může být post-kickoff live kurz)")
elif not df_open.empty:
    st.info("Closing kurzy nejsou k dispozici — všechny snapshoty jsou po výkopu.")
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
