import streamlit as st

from db.queries import get_matches_df, get_line_changes_df
from config import MARKETS_AVAILABLE
from pages.utils import sport_label_map

st.title("Změny kurzů")
st.caption("Přehled detekovaných pohybů kurzů a změn linií mezi snapshoty.")

df_all = get_matches_df()
labels = sport_label_map(df_all)

# ── Filtry ────────────────────────────────────────────────────────────────────
with st.container(border=True):
    fc0, fc1, fc2, fc3 = st.columns(4)

    with fc0:
        available_sports = sorted(labels.keys())
        sport_filter = st.multiselect(
            "Soutěž", available_sports,
            format_func=lambda k: labels.get(k, k),
            placeholder="Všechny",
        )

    df_matches = df_all[df_all["sport_key"].isin(sport_filter)] if sport_filter else df_all

    match_options = {"Všechny zápasy": None}
    if not df_matches.empty:
        for _, row in df_matches.iterrows():
            match_options[f"{row['home_team']} vs {row['away_team']}"] = row["id"]

    with fc1:
        sel_match = st.selectbox("Zápas", list(match_options.keys()))
        match_id  = match_options[sel_match]

    df = get_line_changes_df(match_id)

    with fc2:
        markets = ["Všechny"] + (df["market"].unique().tolist() if not df.empty else [])
        sel_market = st.selectbox(
            "Trh", markets,
            format_func=lambda k: MARKETS_AVAILABLE.get(k, k) if k != "Všechny" else k,
        )
    with fc3:
        available_books = df["bookmaker"].unique().tolist() if not df.empty else []
        books = ["Všichni"] + available_books
        default_book_idx = books.index("pinnacle") if "pinnacle" in books else 0
        sel_book = st.selectbox("Bookmaker", books, index=default_book_idx)

if df.empty:
    st.info("Žádné změny ještě nebyly detekovány. Změny se zaznamenají automaticky po každém fetchi.")
    st.stop()

if sel_market != "Všechny":
    df = df[df["market"] == sel_market]
if sel_book != "Všichni":
    df = df[df["bookmaker"] == sel_book]

# ── Metriky ───────────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Celkem změn",  len(df))
m2.metric("Kurz klesl",   int((df["odds_delta"] < 0).sum()))
m3.metric("Kurz vzrostl", int((df["odds_delta"] > 0).sum()))
m4.metric("Změna linie",  int((df["old_line"] != df["new_line"]).sum()) if "old_line" in df.columns else "—")

# ── Tabulka ───────────────────────────────────────────────────────────────────
st.markdown("### Detailní přehled změn")

display = df[[
    "detected_at", "bookmaker", "market", "selection",
    "old_line", "new_line", "old_odds", "new_odds",
    "odds_delta", "minutes_to_kickoff",
]].copy()

display["detected_at"]        = display["detected_at"].str[:16].str.replace("T", " ")
display["market"]             = display["market"].map(lambda k: MARKETS_AVAILABLE.get(k, k))
display["minutes_to_kickoff"] = display["minutes_to_kickoff"].apply(
    lambda x: f"{int(x)} min" if x is not None else "—"
)
display.columns = [
    "Detekováno", "Bookmaker", "Trh", "Výběr",
    "Stará linie", "Nová linie", "Starý kurz", "Nový kurz",
    "Δ kurz", "Do KO",
]

def _color_delta(val) -> str:
    try:
        return "color:#4caf50;font-weight:bold" if float(val) > 0 else "color:#ef5350;font-weight:bold"
    except Exception:
        return ""

col_tbl, col_exp = st.columns([5, 1])
with col_tbl:
    st.dataframe(
        display.style.map(_color_delta, subset=["Δ kurz"]),
        use_container_width=True, hide_index=True,
    )
with col_exp:
    st.download_button(
        "⬇️ CSV", display.to_csv(index=False).encode("utf-8"),
        "line_changes.csv", "text/csv", use_container_width=True,
    )
st.caption(
    "Δ kurz = rozdíl mezi novým a starým kurzem · "
    "Záporný Δ = kurz klesl (bookmaker snižuje nabídku, šarpci sázejí) · "
    "Kladný Δ = kurz vzrostl"
)
