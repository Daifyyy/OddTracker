import pandas as pd
import streamlit as st

from analytics.results import win_rate_by_signal, clv_summary
from db.queries import get_clv_df, get_steam_moves_df, get_matches_df
from config import MARKETS_AVAILABLE
from pages.utils import sport_label_map

st.title("Analytika")
st.caption("Zpětné vyhodnocení: jak pohyby kurzů korelují se skutečnými výsledky?")

labels = sport_label_map(get_matches_df())

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
        market_filter = st.selectbox(
            "Trh",
            ["Všechny"] + list(MARKETS_AVAILABLE.keys()),
            format_func=lambda k: MARKETS_AVAILABLE.get(k, k) if k != "Všechny" else k,
        )
    with fc2:
        min_delta = st.slider("Min. pohyb kurzu (Δ)", 0.01, 0.30, 0.05, step=0.01,
                              help="Minimální absolutní změna kurzu pro zařazení signálu.")

market_arg   = None if market_filter == "Všechny" else market_filter
sport_keys   = sport_filter if sport_filter else None

# ── Win rate ──────────────────────────────────────────────────────────────────
st.markdown("### Win rate po pohybech kurzů")
st.caption("Jak často výsledek odpovídal směru pohybu kurzu? Vyžaduje dokončené zápasy s výsledky.")

df_wr = win_rate_by_signal(min_odds_delta=min_delta, market=market_arg)

if df_wr.empty:
    st.info(
        "Nedostatek dat. Win rate vyžaduje dokončené zápasy se uloženými výsledky. "
        "Přejdi na Matches → **Fetch výsledky** po skončení zápasů."
    )
else:
    df_wr["Signál"] = df_wr["selection"] + " · kurz " + df_wr["direction"]

    def _color_wr(val) -> str:
        try:
            v = float(str(val).replace(" %", ""))
            if v >= 60: return "color:#4caf50;font-weight:bold"
            if v <= 45: return "color:#ef5350"
            return ""
        except Exception:
            return ""

    display_wr = df_wr[["Signál", "market", "count", "wins", "hit_rate_pct"]].copy()
    display_wr["market"]       = display_wr["market"].map(lambda k: MARKETS_AVAILABLE.get(k, k))
    display_wr["hit_rate_pct"] = display_wr["hit_rate_pct"].astype(str) + " %"
    display_wr.columns         = ["Signál", "Trh", "Počet", "Zásahy", "Hit rate"]

    st.dataframe(
        display_wr.style.map(_color_wr, subset=["Hit rate"]),
        use_container_width=True, hide_index=True,
    )
    st.caption("🟢 ≥ 60 % = potenciálně zajímavý signál · ≤ 45 % = pod náhodou · n < 20 = nedostatečný vzorek")

# ── CLV přehled ───────────────────────────────────────────────────────────────
st.markdown("### CLV přehled")

df_clv = get_clv_df()
if sport_keys:
    df_clv = df_clv[df_clv["sport_key"].isin(sport_keys)]
if market_arg:
    df_clv = df_clv[df_clv["market"] == market_arg]

if not df_clv.empty:
    summary = clv_summary()
    if sport_keys or market_arg:
        from analytics.results import clv_summary as _cs
        summary = {
            "count": len(df_clv),
            "avg_clv_pct": round(df_clv["clv_pct"].mean(), 2),
            "beat_closing_pct": round((df_clv["clv_pct"] > 0).mean() * 100, 1),
        }
    m1, m2, m3 = st.columns(3)
    m1.metric("Záznamů", summary["count"])
    m2.metric("Průměrné CLV", f"{summary['avg_clv_pct']:+.2f} %")
    m3.metric("Porazilo closing", f"{summary['beat_closing_pct']} %")

    by_bm = (
        df_clv.groupby("bookmaker")
        .agg(záznamy=("clv_pct", "count"),
             avg_clv=("clv_pct", "mean"),
             beat_pct=("clv_pct", lambda x: (x > 0).mean() * 100))
        .round(2)
        .reset_index()
        .sort_values("avg_clv", ascending=False)
    )
    by_bm.columns = ["Bookmaker", "Záznamy", "Průměrné CLV %", "% porazilo closing"]

    def _color_clv_bm(val) -> str:
        try:
            return "color:#4caf50" if float(val) > 0 else "color:#ef5350"
        except Exception:
            return ""

    st.dataframe(
        by_bm.style.map(_color_clv_bm, subset=["Průměrné CLV %"]),
        use_container_width=True, hide_index=True,
    )
    st.caption("Pinnacle jako reference: kladné CLV vůči Pinnacle = nejsilnější signál hodnoty.")
else:
    st.info("Žádné CLV záznamy. CLV se vypočítá po dokončení zápasů.")

# ── Steam moves souhrn ────────────────────────────────────────────────────────
st.markdown("### Steam moves (posledních 30 dní)")

df_steam = get_steam_moves_df(hours=720)
if sport_keys:
    df_steam = df_steam[df_steam["sport_key"].isin(sport_keys)]

if not df_steam.empty:
    m1, m2, m3 = st.columns(3)
    m1.metric("Celkem steam moves", len(df_steam))
    m2.metric("Dolů", int((df_steam["direction"] == "down").sum()))
    m3.metric("Nahoru", int((df_steam["direction"] == "up").sum()))

    by_mkt = (
        df_steam.groupby(["market", "direction"])
        .size()
        .reset_index(name="count")
    )
    by_mkt["market"] = by_mkt["market"].map(lambda k: MARKETS_AVAILABLE.get(k, k))
    by_mkt.columns   = ["Trh", "Směr", "Počet"]

    def _color_dir(val: str) -> str:
        return "color:#ef5350;font-weight:bold" if val == "down" else "color:#4caf50"

    st.dataframe(
        by_mkt.style.map(_color_dir, subset=["Směr"]),
        use_container_width=True, hide_index=True,
    )
else:
    st.info("Žádné steam moves v posledních 30 dnech.")

# ── Time-to-kickoff distribuce ────────────────────────────────────────────────
st.markdown("### Pohyby kurzů podle vzdálenosti od výkopu")
st.caption("Kdy se pohyby nejčastěji vyskytují? Blíže k výkopu = ostrá akce.")

from db.queries import get_line_changes_df as _get_lc
df_lc_all = _get_lc()
if sport_keys:
    pass  # line_changes nemají sport_key — nelze filtrovat bez joinu; zobrazujeme vše
if not df_lc_all.empty and "minutes_to_kickoff" in df_lc_all.columns:
    df_lc_tko = df_lc_all.dropna(subset=["minutes_to_kickoff"]).copy()
    if not df_lc_tko.empty:
        bins   = [0, 60, 360, 720, 1440, float("inf")]
        labels_tko = ["< 1h", "1–6h", "6–12h", "12–24h", "> 24h"]
        df_lc_tko["Před výkopem"] = pd.cut(
            df_lc_tko["minutes_to_kickoff"], bins=bins, labels=labels_tko, right=False
        )
        tko_dist = (
            df_lc_tko.groupby("Před výkopem", observed=True)
            .agg(
                Počet=("odds_delta", "count"),
                Prům_delta=("odds_delta", lambda x: x.abs().mean()),
            )
            .round(3)
            .reset_index()
        )
        tko_dist.columns = ["Před výkopem", "Počet pohybů", "Průměrný |Δ|"]
        st.dataframe(tko_dist, use_container_width=True, hide_index=True)
        st.caption("Pohyby těsně před výkopem (< 1h) jsou zpravidla nejsilnějším signálem.")
    else:
        st.info("Nedostatek dat s informací o vzdálenosti od výkopu.")
else:
    st.info("Žádné detekované pohyby kurzů.")
