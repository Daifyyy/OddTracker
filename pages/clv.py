import pandas as pd
import streamlit as st

from db.queries import get_clv_df, get_config
from analytics.results import clv_summary
from config import MARKETS_AVAILABLE

st.title("CLV — Closing Line Value")
st.caption("Porovnání opening kurzů s closing kurzy. Kladné CLV = tvůj kurz byl lepší než závěrečný.")

sport_key = get_config("active_sport_key")
df = get_clv_df(sport_key)

if df.empty:
    st.info("Žádné CLV záznamy. CLV se vypočítá automaticky po dokončení zápasů.")
    st.stop()

# ── Metriky ───────────────────────────────────────────────────────────────────
summary = clv_summary(sport_key)
m1, m2, m3 = st.columns(3)
m1.metric("Celkem záznamů", summary["count"])
m2.metric("Průměrné CLV", f"{summary['avg_clv_pct']:+.2f} %",
          help="Průměrný procentuální rozdíl mezi opening a closing kurzem.")
m3.metric("Porazilo closing line", f"{summary['beat_closing_pct']} %",
          help="Jak často byl opening kurz lepší než closing.")

# ── Filtry ────────────────────────────────────────────────────────────────────
with st.container(border=True):
    fc1, fc2 = st.columns(2)
    with fc1:
        markets = ["Všechny"] + df["market"].unique().tolist()
        market_filter = st.selectbox(
            "Trh", markets,
            format_func=lambda k: MARKETS_AVAILABLE.get(k, k) if k != "Všechny" else k,
        )
    with fc2:
        min_clv = st.slider("Min. CLV %", -20, 20, -20)

if market_filter != "Všechny":
    df = df[df["market"] == market_filter]
df = df[df["clv_pct"] >= min_clv]

# ── CLV distribuce ────────────────────────────────────────────────────────────
st.markdown("### Distribuce CLV")

buckets = pd.cut(
    df["clv_pct"],
    bins=[-99, -10, -5, -2, 0, 2, 5, 10, 99],
    labels=["< -10 %", "-10 až -5 %", "-5 až -2 %", "-2 až 0 %",
            "0 až +2 %", "+2 až +5 %", "+5 až +10 %", "> +10 %"],
)
dist = buckets.value_counts().sort_index().reset_index()
dist.columns = ["CLV pásmo", "Počet"]
dist["Podíl"] = (dist["Počet"] / dist["Počet"].sum() * 100).round(1).astype(str) + " %"

def _color_bucket(val: str) -> str:
    if val.startswith("+") or val.startswith("0"):
        return "color:#4caf50"
    return "color:#ef5350"

st.dataframe(
    dist.style.applymap(_color_bucket, subset=["CLV pásmo"]),
    use_container_width=True, hide_index=True,
)

# ── Detailní tabulka ──────────────────────────────────────────────────────────
st.markdown("### Detailní záznamy")

display = df[[
    "home_team", "away_team", "bookmaker", "market",
    "selection", "line", "tracked_odds", "closing_odds",
    "clv_raw", "clv_pct", "tracked_at",
]].copy()
display["Zápas"]     = display["home_team"] + " vs " + display["away_team"]
display["tracked_at"] = display["tracked_at"].str[:16].str.replace("T", " ")
display["market"]    = display["market"].map(lambda k: MARKETS_AVAILABLE.get(k, k))
display = display[[
    "Zápas", "bookmaker", "market", "selection", "line",
    "tracked_odds", "closing_odds", "clv_raw", "clv_pct", "tracked_at",
]]
display.columns = [
    "Zápas", "Bookmaker", "Trh", "Výběr", "Linie",
    "Opening", "Closing", "CLV abs.", "CLV %", "Zaznamenáno",
]

def _color_clv(val) -> str:
    try:
        return "color:#4caf50;font-weight:bold" if float(val) > 0 else "color:#ef5350"
    except Exception:
        return ""

st.dataframe(
    display.style
        .applymap(_color_clv, subset=["CLV %", "CLV abs."])
        .format({"Opening": "{:.2f}", "Closing": "{:.2f}",
                 "CLV abs.": "{:+.3f}", "CLV %": "{:+.2f}"},
                na_rep="—"),
    use_container_width=True, hide_index=True,
)
st.caption(
    "CLV % = (opening / closing − 1) × 100 · "
    "Kladná hodnota = opening byl lepší než closing = potenciálně hodnotná sázka"
)
