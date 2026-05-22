from datetime import datetime, timezone

import streamlit as st

from db.queries import get_movement_overview, get_steam_moves_df, get_matches_df
from config import MARKETS_AVAILABLE
from pages.utils import sport_label_map

st.title("Pohyby kurzů")
st.caption("Pinnacle opening → aktuální kurz pro všechny aktivní zápasy. Seřazeno: největší pokles nahoře.")

df = get_movement_overview()

if df.empty:
    st.info("Žádná data. Pro zobrazení pohybů jsou potřeba alespoň 2 snapshoty — fetchni preset dvakrát.")
    st.stop()

# ── Výpočet pohybu ────────────────────────────────────────────────────────────
df["delta"]     = df["current_odds"] - df["opening_odds"]
df["delta_pct"] = ((df["current_odds"] / df["opening_odds"]) - 1) * 100

# ── Steam badge ───────────────────────────────────────────────────────────────
df_steam = get_steam_moves_df(hours=48)
steam_keys: set = set()
if not df_steam.empty:
    for _, r in df_steam.iterrows():
        steam_keys.add((r["match_id"], r["market"], r["selection"]))

df["signal"] = df.apply(
    lambda r: "🚨 Steam" if (r["match_id"], r["market"], r["selection"]) in steam_keys else "",
    axis=1,
)

# ── Do výkopu ─────────────────────────────────────────────────────────────────
now = datetime.now(timezone.utc)
df["ko_h"] = df["commence_time"].apply(
    lambda t: round(
        (datetime.fromisoformat(t.replace("Z", "+00:00")) - now).total_seconds() / 3600, 1
    )
)

# ── Filtry ────────────────────────────────────────────────────────────────────
labels = sport_label_map(get_matches_df())

with st.container(border=True):
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        markets_av = ["Všechny"] + sorted(df["market"].unique().tolist())
        sel_market = st.selectbox(
            "Trh", markets_av,
            format_func=lambda k: MARKETS_AVAILABLE.get(k, k) if k != "Všechny" else k,
        )
    with fc2:
        min_pct = st.slider("Min. pohyb %", 0, 20, 2)
    with fc3:
        direction = st.selectbox("Směr", ["Vše", "Pokles", "Nárůst"])
    with fc4:
        max_ko = st.number_input("Do KO max (h)", min_value=0, max_value=999, value=0,
                                 help="0 = bez omezení")

df_f = df.copy()
if sel_market != "Všechny":
    df_f = df_f[df_f["market"] == sel_market]
df_f = df_f[df_f["delta_pct"].abs() >= min_pct]
if direction == "Pokles":
    df_f = df_f[df_f["delta"] < 0]
elif direction == "Nárůst":
    df_f = df_f[df_f["delta"] > 0]
if max_ko > 0:
    df_f = df_f[df_f["ko_h"].apply(lambda h: 0 <= h <= max_ko)]

if df_f.empty:
    st.info("Žádné pohyby pro zadaný filtr.")
    st.stop()

# ── Seřazení: největší pokles nahoře ─────────────────────────────────────────
df_f = df_f.sort_values("delta_pct", ascending=True)

# ── Příprava zobrazení ────────────────────────────────────────────────────────
df_f["Zápas"]  = df_f["home_team"] + " vs " + df_f["away_team"]
df_f["Liga"]   = df_f["sport_key"].map(lambda k: labels.get(k, k))
df_f["Trh"]    = df_f["market"].map(lambda k: MARKETS_AVAILABLE.get(k, k))
df_f["Výběr"]  = df_f.apply(
    lambda r: f"{r['selection']} {r['line']:g}".strip() if r["line"] is not None else r["selection"],
    axis=1,
)
df_f["Do KO"]  = df_f["ko_h"].apply(lambda h: f"{h:.1f}h" if h >= 0 else "—")

display = df_f[[
    "signal", "Zápas", "Liga", "Trh", "Výběr",
    "opening_odds", "current_odds", "delta", "delta_pct", "Do KO",
]].copy()
display.columns = [
    "Signal", "Zápas", "Liga", "Trh", "Výběr",
    "Opening", "Nyní", "Δ", "Δ %", "Do KO",
]

# ── Metriky ───────────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Záznamů celkem", len(display))
m2.metric("Poklesů", int((df_f["delta"] < 0).sum()))
m3.metric("Nárůstů", int((df_f["delta"] > 0).sum()))
m4.metric("Steam signálů", int((df_f["signal"] != "").sum()))

# ── Barevné zvýraznění Δ % ────────────────────────────────────────────────────
def _color_pct(val) -> str:
    try:
        v = float(str(val).replace("%", "").replace("+", ""))
        if v <= -5:
            return "background-color:#5a1a1a;color:white;font-weight:bold"
        if v <= -2:
            return "background-color:#3a1b1b;color:#ef5350;font-weight:bold"
        if v >= 5:
            return "background-color:#1a3a1a;color:white;font-weight:bold"
        if v >= 2:
            return "background-color:#1b3a2a;color:#4caf50"
    except Exception:
        pass
    return ""

def _color_delta(val) -> str:
    try:
        v = float(val)
        if v < 0:
            return "color:#ef5350;font-weight:bold"
        if v > 0:
            return "color:#4caf50;font-weight:bold"
    except Exception:
        pass
    return ""

st.dataframe(
    display.style
        .map(_color_pct,   subset=["Δ %"])
        .map(_color_delta, subset=["Δ"])
        .format({
            "Opening": "{:.2f}",
            "Nyní":    "{:.2f}",
            "Δ":       "{:+.2f}",
            "Δ %":     "{:+.1f}%",
        }, na_rep="—"),
    use_container_width=True,
    hide_index=True,
)
st.caption(
    "🔴 Δ % ≤ −5 % = silný signál poklesu (ostrá sázka)  |  "
    "🚨 Steam = koordinovaný pohyb u 3+ bookmakrů  |  "
    "Seřazeno od největšího poklesu"
)
