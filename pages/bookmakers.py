import pandas as pd
import streamlit as st

from db.queries import (
    get_matches_df, get_latest_odds_per_book,
    get_config, get_snapshots_df,
)
from config import MARKETS_AVAILABLE

st.title("Porovnání bookmakrů")
st.caption("Aktuální kurzy napříč bookmakery a historický vývoj pro jeden výběr.")

sport_key  = get_config("active_sport_key", "soccer_germany_bundesliga")
df_matches = get_matches_df(sport_key)

if df_matches.empty:
    st.info("Žádné zápasy. Přejdi na **Matches** a fetchni kurzy.")
    st.stop()

df_matches["label"] = df_matches["home_team"] + " vs " + df_matches["away_team"]

# ── Filtry ────────────────────────────────────────────────────────────────────
with st.container(border=True):
    fc1, fc2 = st.columns(2)
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
            st.info("Pro tento zápas nejsou snapshoty.")
            st.stop()
        market = st.selectbox(
            "Trh",
            df_snap["market"].unique().tolist(),
            format_func=lambda k: MARKETS_AVAILABLE.get(k, k),
        )

df_latest = get_latest_odds_per_book(match_id, market)
if df_latest.empty:
    st.info("Žádné aktuální kurzy.")
    st.stop()

# ── Aktuální kurzy: pivot bookmaker × výběr ───────────────────────────────────
st.markdown("### Aktuální kurzy — poslední snapshot")

pivot = df_latest.pivot_table(
    index="bookmaker", columns="selection", values="odds", aggfunc="first"
)
pivot.index.name   = "Bookmaker"
pivot.columns.name = ""

def _best(s: pd.Series) -> list[str]:
    return [
        "background-color:#1b3a2a;font-weight:bold" if v == s.max() else ""
        for v in s
    ]

st.dataframe(
    pivot.style.apply(_best).format("{:.2f}", na_rep="—"),
    use_container_width=True,
)
st.caption("🟢 Tučně = nejvyšší kurz na daný výběr")

# ── Best / Worst přehled ──────────────────────────────────────────────────────
st.markdown("### Nejlepší a nejhorší kurzy")

rows = []
for sel, grp in df_latest.groupby("selection"):
    best  = grp.loc[grp["odds"].idxmax()]
    worst = grp.loc[grp["odds"].idxmin()]
    rows.append({
        "Výběr":        sel,
        "Linie":        best.get("line"),
        "Nejlepší":     best["odds"],
        "U koho":       best["bookmaker"],
        "Nejhorší":     worst["odds"],
        "U koho ":      worst["bookmaker"],
        "Spread":       round(best["odds"] - worst["odds"], 3),
    })

st.dataframe(
    pd.DataFrame(rows).style.format(
        {"Nejlepší": "{:.2f}", "Nejhorší": "{:.2f}", "Spread": "{:.3f}"},
        na_rep="—",
    ),
    use_container_width=True, hide_index=True,
)
st.caption("Spread = rozdíl mezi nejlepším a nejhorším kurzem. Větší spread = více prostoru pro výběr.")

# ── Historický vývoj u konkrétního výběru ────────────────────────────────────
st.markdown("### Historický vývoj výběru")

selections    = df_snap[df_snap["market"] == market]["selection"].unique().tolist()
selected_sel  = st.selectbox("Výběr", selections)

hist = df_snap[
    (df_snap["market"] == market) &
    (df_snap["selection"] == selected_sel)
].copy()
hist["čas"] = hist["snapshot_time"].str[11:16]

pivot_hist = hist.pivot_table(
    index="čas", columns="bookmaker", values="odds", aggfunc="first"
)
pivot_hist.index.name   = "Čas (UTC)"
pivot_hist.columns.name = ""

def _hl(df: pd.DataFrame) -> pd.DataFrame:
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for col in df.columns:
        for i in range(1, len(df)):
            prev, curr = df[col].iloc[i - 1], df[col].iloc[i]
            if pd.notna(prev) and pd.notna(curr) and curr != prev:
                styles.iloc[i][col] = (
                    "background-color:#1b3a2a;font-weight:bold" if curr > prev
                    else "background-color:#3a1b1b;font-weight:bold"
                )
    return styles

st.dataframe(
    pivot_hist.style.apply(_hl, axis=None).format("{:.2f}", na_rep="—"),
    use_container_width=True,
)
st.caption("Každý sloupec = jeden bookmaker · Každý řádek = jeden snapshot v čase")
