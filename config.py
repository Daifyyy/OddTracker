from pathlib import Path

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Markets confirmed available via The Odds API (EU region, soccer).
# NOTE: corners, btts, alternate_totals, team_totals are NOT offered by this API.
MARKETS_AVAILABLE = {
    "h2h":     "1X2 (Match Result)",
    "totals":  "Over/Under goals",
    "spreads": "Asian Handicap",
}

# Bookmakers confirmed present in The Odds API EU region for soccer.
# NOTE: bet365, Fortuna, Betano, Tipsport are NOT available in this API.
BOOKMAKERS_AVAILABLE = [
    "pinnacle",
    "williamhill",
    "nordicbet",
    "betsson",
    "marathonbet",
    "winamax_de",
    "sport888",
    "unibet_fr",
    "betonlineag",
    "gtbets",
    "everygame",
    "suprabets",
]

# Default bookmakers for fetch — Pinnacle (reference) + 2 soft books for steam detection.
# Steam requires min 3 books; this trio is the recommended minimum.
BOOKMAKERS_DEFAULT = ["pinnacle", "williamhill", "nordicbet"]

REGIONS_AVAILABLE = {
    "eu": "Europe",
    "uk": "United Kingdom",
    "us": "United States",
    "au": "Australia",
}

STEAM_MIN_BOOKS      = 3
STEAM_MIN_ODDS_DELTA = 0.05
STEAM_WINDOW_MINUTES = 15

DB_PATH  = Path(__file__).parent / "oddtracker.db"
LOG_DIR  = Path(__file__).parent / "logs"

PLOTLY_BGCOLOR       = "#0E1117"
PLOTLY_PAPER_BGCOLOR = "#0E1117"
APP_THEME            = "plotly_dark"
