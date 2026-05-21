import streamlit as st

from db.models import init_db
from db.queries import get_config

st.set_page_config(
    page_title="OddTracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    init_db()
except Exception as e:
    st.error(f"**DB init failed:** {e}")
    st.stop()

with st.sidebar:
    st.markdown("## 📊 OddTracker")
    st.caption("Sports market movement tracker")
    st.divider()
    credits = get_config("credits_remaining")
    if credits is not None:
        color = "🟢" if credits > 100 else ("🟡" if credits > 20 else "🔴")
        st.metric(f"{color} API kredity", credits)
    else:
        st.caption("Kredity: fetchni pro aktualizaci")

    from db.queries import get_matches_df as _gmdf
    active_count = len(_gmdf(only_active=True))
    st.metric("Aktivní zápasy", active_count)

    last_fetch = get_config("last_fetch_at")
    if last_fetch:
        from datetime import datetime as _dt
        fetch_dt = _dt.fromisoformat(last_fetch)
        st.caption(f"Poslední fetch: {fetch_dt.strftime('%d.%m %H:%M')}")
    else:
        st.caption("Poslední fetch: —")

pg = st.navigation([
    st.Page("pages/matches.py",    title="Matches",        icon="⚽", default=True),
    st.Page("pages/movement.py",   title="Vývoj kurzů",    icon="📈"),
    st.Page("pages/lines.py",      title="Změny kurzů",    icon="↕"),
    st.Page("pages/bookmakers.py", title="Bookmakeři",     icon="🏦"),
    st.Page("pages/clv.py",        title="CLV",            icon="🎯"),
    st.Page("pages/steam.py",      title="Steam Moves",    icon="🚨"),
    st.Page("pages/analytics.py",  title="Analytika",      icon="📊"),
    st.Page("pages/help.py",       title="Průvodce",       icon="❓"),
])
pg.run()
