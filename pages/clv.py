import pandas as pd
import streamlit as st

from db.queries import get_clv_df, get_matches_df
from analytics.results import clv_summary
from config import MARKETS_AVAILABLE
from pages.utils import sport_label_map, to_local_str

st.title("CLV — Closing Line Value")
st.caption("Porovnání opening kurzů s closing kurzy. Kladné CLV = tvůj kurz byl lepší než závěrečný.")

df = get_clv_df()

if df.empty:
    st.info("Žádné CLV záznamy. CLV se vypočítá automaticky po dokončení zápasů.")
    st.stop()

labels = sport_label_map(get_matches_df())

# ── Metriky (celkové) ─────────────────────────────────────────────────────────
summary_all = clv_summary()
m1, m2, m3 = st.columns(3)
m1.metric("Celkem záznamů", summary_all["count"])
m2.metric("Průměrné CLV", f"{summary_all['avg_clv_pct']:+.2f} %",
          help="Průměrný procentuální rozdíl mezi opening a closing kurzem.")
m3.metric("Porazilo closing line", f"{summary_all['beat_closing_pct']} %",
          help="Jak často byl opening kurz lepší než closing.")

# ── Filtry ────────────────────────────────────────────────────────────────────
with st.container(border=True):
    fc0, fc1, fc2 = st.columns(3)
    with fc0:
        available_sports = sorted(labels.keys())
        sport_filter = st.multiselect(
            "Soutěž", available_sports,
            format_func=lambda k: labels.get(k, k),
            placeholder="Všechny",
        )
    with fc1:
        markets = ["Všechny"] + df["market"].unique().tolist()
        market_filter = st.selectbox(
            "Trh", markets,
            format_func=lambda k: MARKETS_AVAILABLE.get(k, k) if k != "Všechny" else k,
        )
    with fc2:
        min_clv = st.slider("Min. CLV %", -20, 20, -20)

if sport_filter:
    df = df[df["sport_key"].isin(sport_filter)]
if market_filter != "Všechny":
    df = df[df["market"] == market_filter]
df = df[df["clv_pct"] >= min_clv]

if df.empty:
    st.info("Žádné záznamy pro zvolené filtry.")
    st.stop()

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
    dist.style.map(_color_bucket, subset=["CLV pásmo"]),
    use_container_width=True, hide_index=True,
)

# ── Detailní tabulka ──────────────────────────────────────────────────────────
st.markdown("### Detailní záznamy")

display = df[[
    "home_team", "away_team", "bookmaker", "market",
    "selection", "line", "tracked_odds", "closing_odds",
    "clv_raw", "clv_pct", "tracked_at",
]].copy()
display["Zápas"]      = display["home_team"] + " vs " + display["away_team"]
display["tracked_at"] = to_local_str(display["tracked_at"])
display["market"]     = display["market"].map(lambda k: MARKETS_AVAILABLE.get(k, k))
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

col_tbl, col_exp = st.columns([5, 1])
with col_tbl:
    st.dataframe(
        display.style
            .map(_color_clv, subset=["CLV %", "CLV abs."])
            .format({"Opening": "{:.2f}", "Closing": "{:.2f}",
                     "CLV abs.": "{:+.3f}", "CLV %": "{:+.2f}"},
                    na_rep="—"),
        use_container_width=True, hide_index=True,
    )
with col_exp:
    st.download_button(
        "⬇️ CSV", display.to_csv(index=False).encode("utf-8"),
        "clv_records.csv", "text/csv", use_container_width=True,
    )
st.caption(
    "CLV % = (opening / closing − 1) × 100 · "
    "Kladná hodnota = opening byl lepší než closing = potenciálně hodnotná sázka"
)
