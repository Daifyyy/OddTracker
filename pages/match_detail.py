import pandas as pd
import streamlit as st

from db.queries import (
    get_matches_df, get_snapshots_df, get_opening_odds, get_closing_odds,
    get_line_changes_df, get_steam_moves_df, get_clv_df,
)
from config import MARKETS_AVAILABLE
from pages.utils import highlight_pivot, sport_label_map, to_local_str

if "selected_match_id" not in st.session_state:
    st.warning("Žádný zápas není vybrán.")
    if st.button("← Zpět na Matches"):
        st.switch_page("pages/matches.py")
    st.stop()

match_id    = st.session_state.selected_match_id
match_label = st.session_state.get("selected_match_label", match_id)

df_all = get_matches_df()
match_rows = df_all[df_all["id"] == match_id]
if match_rows.empty:
    st.error("Zápas nenalezen v databázi.")
    st.stop()
match_row = match_rows.iloc[0]

labels  = sport_label_map(df_all)
league  = labels.get(match_row["sport_key"], match_row["sport_key"])
kickoff = match_row["commence_time"][:16].replace("T", " ")

col_back, col_info = st.columns([1, 5])
with col_back:
    if st.button("← Zpět"):
        st.switch_page("pages/matches.py")
with col_info:
    st.markdown(f"## {match_label}")
    st.caption(f"🏆 {league}  ·  ⏰ Výkop: {kickoff} UTC")

st.divider()

tab_odds, tab_changes, tab_steam, tab_clv = st.tabs([
    "📋 Přehled kurzů", "📈 Změny kurzů", "🚨 Steam", "📊 CLV"
])

# ── Tab: Přehled kurzů ────────────────────────────────────────────────────────
with tab_odds:
    df_snap = get_snapshots_df(match_id)

    if df_snap.empty:
        st.info("Žádné snapshoty pro tento zápas. Fetchni preset, který ho obsahuje.")
    else:
        markets_av = df_snap["market"].unique().tolist()
        books_av   = sorted(df_snap["bookmaker"].unique().tolist())

        fc1, fc2 = st.columns(2)
        with fc1:
            market = st.selectbox(
                "Trh", markets_av,
                format_func=lambda k: MARKETS_AVAILABLE.get(k, k),
                key="det_market",
            )
        with fc2:
            default_book = "pinnacle" if "pinnacle" in books_av else books_av[0]
            bookmaker = st.selectbox(
                "Bookmaker", books_av,
                index=books_av.index(default_book),
                key="det_book",
            )

        filt_all = df_snap[
            (df_snap["market"] == market) &
            (df_snap["bookmaker"] == bookmaker)
        ].copy()
        filt = filt_all[filt_all["snapshot_time"] <= match_row["commence_time"]].copy()
        post_ko_count = len(filt_all) - len(filt)

        if filt.empty:
            st.info("Žádné pre-kickoff snapshoty pro tento bookmaker a trh.")
        else:
            available_lines = sorted(filt["line"].dropna().unique().tolist())
            selected_line = None
            if available_lines:
                selected_line = st.selectbox(
                    "Linie", available_lines,
                    format_func=lambda x: f"{x:g}",
                    key="det_line",
                )
                filt = filt[filt["line"] == selected_line]

            filt["sel_col"] = filt["selection"]
            filt["čas"] = to_local_str(filt["snapshot_time"])
            _tz_label = "Čas (Praha)"

            pivot = filt.pivot_table(
                index="čas", columns="sel_col", values="odds", aggfunc="first"
            )
            pivot.index.name   = _tz_label
            pivot.columns.name = ""

            st.markdown(f"### Vývoj kurzů — {bookmaker.capitalize()}")
            st.dataframe(
                pivot.style
                    .apply(highlight_pivot, axis=None)
                    .format("{:.2f}", na_rep="—"),
                use_container_width=True,
            )
            commence_str = match_row["commence_time"][:16].replace("T", " ")
            cap = f"🟢 Kurz vzrostl  |  🔴 Kurz klesl  |  Poslední řádek = Closing  |  Výkop: {commence_str} UTC"
            if post_ko_count > 0:
                cap += f"  |  ⚠️ {post_ko_count} post-kickoff snapshot(ů) skryto"
            st.caption(cap)

            df_open  = get_opening_odds(match_id, market)
            df_close = get_closing_odds(match_id, market)

            df_open_b  = df_open[df_open["bookmaker"] == bookmaker].copy() if not df_open.empty else pd.DataFrame()
            df_close_b = df_close[df_close["bookmaker"] == bookmaker].copy() if not df_close.empty else pd.DataFrame()
            if selected_line is not None and not df_open_b.empty:
                df_open_b = df_open_b[df_open_b["line"] == selected_line]
            if selected_line is not None and not df_close_b.empty:
                df_close_b = df_close_b[df_close_b["line"] == selected_line]

            if not df_open_b.empty and not df_close_b.empty:
                merged = df_open_b.merge(
                    df_close_b,
                    on=["bookmaker", "market", "selection", "line"],
                    suffixes=("_open", "_close"),
                )
                merged["Pohyb"] = (merged["odds_close"] - merged["odds_open"]).apply(
                    lambda x: f"{x:+.2f}"
                )
                merged["čas_open"]  = to_local_str(merged["snapshot_time_open"])
                merged["čas_close"] = to_local_str(merged["snapshot_time_close"])
                disp_oc = merged[["selection", "line",
                                   "čas_open", "odds_open",
                                   "čas_close", "odds_close", "Pohyb"]].copy()
                disp_oc.columns = ["Výběr", "Linie",
                                   "Čas Opening", "Opening",
                                   "Čas Closing", "Closing", "Pohyb"]

                def _color_pohyb(val: str) -> str:
                    if str(val).startswith("+"):
                        return "color:#4caf50;font-weight:bold"
                    if str(val).startswith("-"):
                        return "color:#ef5350;font-weight:bold"
                    return ""

                st.markdown("### Opening vs Closing")
                st.dataframe(
                    disp_oc.style
                        .map(_color_pohyb, subset=["Pohyb"])
                        .format({"Opening": "{:.2f}", "Closing": "{:.2f}"}, na_rep="—"),
                    use_container_width=True, hide_index=True,
                )
                st.caption("Closing = poslední fetch PŘED výkopem — v pivotu výše může být poslední řádek post-kickoff live kurz")

# ── Tab: Změny kurzů ──────────────────────────────────────────────────────────
with tab_changes:
    df_lc = get_line_changes_df(match_id)

    if df_lc.empty:
        st.info("Žádné změny kurzů pro tento zápas.")
    else:
        fc_lc1, fc_lc2 = st.columns(2)
        with fc_lc1:
            markets_lc = df_lc["market"].unique().tolist()
            market_lc  = st.selectbox(
                "Trh", ["Všechny"] + markets_lc,
                format_func=lambda k: MARKETS_AVAILABLE.get(k, k) if k != "Všechny" else k,
                key="det_lc_market",
            )
        if market_lc != "Všechny":
            df_lc = df_lc[df_lc["market"] == market_lc]

        with fc_lc2:
            books_lc = sorted(df_lc["bookmaker"].unique().tolist())
            default_lc_book = "pinnacle" if "pinnacle" in books_lc else (books_lc[0] if books_lc else None)
            book_lc_idx = (books_lc.index(default_lc_book) + 1) if default_lc_book else 0
            book_lc = st.selectbox(
                "Bookmaker", ["Všichni"] + books_lc, index=book_lc_idx,
                key="det_lc_book",
            )
        if book_lc != "Všichni":
            df_lc = df_lc[df_lc["bookmaker"] == book_lc]

        m1, m2, m3 = st.columns(3)
        m1.metric("Celkem změn",   len(df_lc))
        m2.metric("Kurz klesl",    int((df_lc["odds_delta"] < 0).sum()))
        m3.metric("Kurz vzrostl",  int((df_lc["odds_delta"] > 0).sum()))

        disp_lc = df_lc[[
            "detected_at", "bookmaker", "market", "selection",
            "old_odds", "new_odds", "odds_delta", "minutes_to_kickoff",
        ]].copy()
        disp_lc["detected_at"] = to_local_str(disp_lc["detected_at"])
        disp_lc["market"]             = disp_lc["market"].map(lambda k: MARKETS_AVAILABLE.get(k, k))
        disp_lc["minutes_to_kickoff"] = disp_lc["minutes_to_kickoff"].apply(
            lambda x: f"{int(x)} min" if x is not None else "—"
        )
        disp_lc.columns = [
            "Čas", "Bookmaker", "Trh", "Výběr",
            "Starý kurz", "Nový kurz", "Δ kurz", "Do KO",
        ]

        def _color_delta(val) -> str:
            try:
                return "color:#4caf50;font-weight:bold" if float(val) > 0 else "color:#ef5350;font-weight:bold"
            except Exception:
                return ""

        st.dataframe(
            disp_lc.style
                .map(_color_delta, subset=["Δ kurz"])
                .format({"Starý kurz": "{:.2f}", "Nový kurz": "{:.2f}", "Δ kurz": "{:+.2f}"}, na_rep="—"),
            use_container_width=True, hide_index=True,
        )

# ── Tab: Steam ────────────────────────────────────────────────────────────────
with tab_steam:
    df_steam_all = get_steam_moves_df(hours=8760)
    df_steam = (
        df_steam_all[df_steam_all["match_id"] == match_id]
        if not df_steam_all.empty else pd.DataFrame()
    )

    if df_steam.empty:
        st.info("Žádné steam moves pro tento zápas.")
    else:
        disp_steam = df_steam[[
            "detected_at", "market", "selection",
            "bookmaker_count", "avg_odds_delta", "direction", "minutes_to_kickoff",
        ]].copy()
        disp_steam["detected_at"]        = to_local_str(disp_steam["detected_at"])
        disp_steam["minutes_to_kickoff"] = disp_steam["minutes_to_kickoff"].apply(
            lambda x: f"{int(x)} min" if x is not None else "—"
        )
        disp_steam.columns = [
            "Čas", "Trh", "Výběr", "Počet books", "Prům. Δ", "Směr", "Do KO",
        ]

        def _color_dir(val: str) -> str:
            return "color:#ef5350;font-weight:bold" if val == "down" else "color:#4caf50;font-weight:bold"

        st.dataframe(
            disp_steam.style
                .map(_color_dir, subset=["Směr"])
                .format({"Prům. Δ": "{:+.2f}"}, na_rep="—"),
            use_container_width=True, hide_index=True,
        )
        st.caption("🔴 Dolů = kurz klesl u více bookmakrů → signál ostrých peněz")

# ── Tab: CLV ──────────────────────────────────────────────────────────────────
with tab_clv:
    df_clv_all = get_clv_df()
    df_clv = (
        df_clv_all[df_clv_all["match_id"] == match_id]
        if not df_clv_all.empty else pd.DataFrame()
    )

    if df_clv.empty:
        st.info("Žádné CLV záznamy. CLV se vypočítá automaticky po dokončení zápasu.")
    else:
        disp_clv = df_clv[[
            "bookmaker", "market", "selection", "line",
            "tracked_odds", "closing_odds", "clv_raw", "clv_pct", "tracked_at",
        ]].copy()
        disp_clv["tracked_at"] = to_local_str(disp_clv["tracked_at"])
        disp_clv["market"]     = disp_clv["market"].map(lambda k: MARKETS_AVAILABLE.get(k, k))
        disp_clv.columns = [
            "Bookmaker", "Trh", "Výběr", "Linie",
            "Opening", "Closing", "CLV abs.", "CLV %", "Zaznamenáno",
        ]

        def _color_clv(val) -> str:
            try:
                return "color:#4caf50;font-weight:bold" if float(val) > 0 else "color:#ef5350"
            except Exception:
                return ""

        st.dataframe(
            disp_clv.style
                .map(_color_clv, subset=["CLV %", "CLV abs."])
                .format({"Opening": "{:.2f}", "Closing": "{:.2f}",
                         "CLV abs.": "{:+.3f}", "CLV %": "{:+.2f}"}, na_rep="—"),
            use_container_width=True, hide_index=True,
        )
        st.caption("CLV % = (opening / closing − 1) × 100  ·  Kladná hodnota = opening byl lepší než closing")
