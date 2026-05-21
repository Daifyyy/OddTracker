import streamlit as st

from db.queries import get_steam_moves_df

st.title("Steam moves")
st.caption("Detekce koordinovaných pohybů kurzů u více bookmakrů současně — signál ostrých peněz.")

# ── Filtry ────────────────────────────────────────────────────────────────────
with st.container(border=True):
    fc1, fc2 = st.columns([2, 2])
    with fc1:
        hours = st.select_slider(
            "Časové okno",
            options=[6, 12, 24, 48, 72, 168, 336, 720],
            value=48,
            format_func=lambda h: f"Posledních {h} h" if h < 168 else f"Posledních {h // 24} dní",
        )
    with fc2:
        min_books = st.slider("Min. počet bookmakrů", 2, 5, 3)

df = get_steam_moves_df(hours)
if not df.empty and min_books > 2:
    df = df[df["bookmaker_count"] >= min_books]

if df.empty:
    st.info("Žádné steam moves v zadaném období. Steam moves se detekují automaticky po každém fetchi.")
    st.stop()

# ── Metriky ───────────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Steam moves celkem", len(df))
m2.metric("Dolů (ostrá sázka)", int((df["direction"] == "down").sum()))
m3.metric("Nahoru",              int((df["direction"] == "up").sum()))
m4.metric("Prům. počet books",   f"{df['bookmaker_count'].mean():.1f}")

# ── Tabulka ───────────────────────────────────────────────────────────────────
st.markdown("### Detekované steam moves")

display = df[[
    "detected_at", "home_team", "away_team", "market",
    "selection", "bookmaker_count", "avg_odds_delta",
    "direction", "minutes_to_kickoff",
]].copy()

display["detected_at"] = display["detected_at"].str[:16].str.replace("T", " ")
display["Zápas"]       = display["home_team"] + " vs " + display["away_team"]
display["minutes_to_kickoff"] = display["minutes_to_kickoff"].apply(
    lambda x: f"{int(x)} min" if x is not None else "—"
)

display = display[[
    "detected_at", "Zápas", "market", "selection",
    "bookmaker_count", "avg_odds_delta", "direction", "minutes_to_kickoff",
]]
display.columns = [
    "Detekováno", "Zápas", "Trh", "Výběr",
    "Počet books", "Prům. Δ", "Směr", "Do KO",
]

def _color_dir(val: str) -> str:
    return "color:#ef5350;font-weight:bold" if val == "down" else "color:#4caf50;font-weight:bold"

col_tbl, col_exp = st.columns([5, 1])
with col_tbl:
    st.dataframe(
        display.style.map(_color_dir, subset=["Směr"]),
        use_container_width=True, hide_index=True,
    )
with col_exp:
    st.download_button(
        "⬇️ CSV", display.to_csv(index=False).encode("utf-8"),
        "steam_moves.csv", "text/csv", use_container_width=True,
    )
st.caption(
    "🔴 **Dolů** = kurz klesl u více bookmakrů → typicky ostrá sázka na daný výběr · "
    "🟢 **Nahoru** = kurz vzrostl → veřejné peníze nebo vyrovnání pozice"
)
