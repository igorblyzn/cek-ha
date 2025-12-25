"""Constants for the CEK Power Outage integration."""

DOMAIN = "cek_power_outage"

# Configuration keys
CONF_QUEUE = "queue"
CONF_UPDATE_INTERVAL = "update_interval"

# Defaults
DEFAULT_QUEUE = "6.2"
DEFAULT_UPDATE_INTERVAL = 30  # minutes
MIN_UPDATE_INTERVAL = 5
MAX_UPDATE_INTERVAL = 120

# URLs
CEK_URL = "https://cek.dp.ua/index.php/cpojivaham/vidkliuchennia.html"

# Ukrainian months for date parsing
UKRAINIAN_MONTHS = [
    "СІЧНЯ", "ЛЮТОГО", "БЕРЕЗНЯ", "КВІТНЯ", "ТРАВНЯ", "ЧЕРВНЯ",
    "ЛИПНЯ", "СЕРПНЯ", "ВЕРЕСНЯ", "ЖОВТНЯ", "ЛИСТОПАДА", "ГРУДНЯ",
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]




