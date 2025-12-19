"""Data update coordinator for CEK Power Outage."""
from __future__ import annotations

import logging
import re
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CEK_URL,
    CONF_QUEUE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_QUEUE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    UKRAINIAN_MONTHS,
)

_LOGGER = logging.getLogger(__name__)


class TextExtractor(HTMLParser):
    """Simple HTML parser that extracts text content."""

    def __init__(self) -> None:
        """Initialize the parser."""
        super().__init__()
        self.text_parts: list[str] = []
        self._skip_tags = {"script", "style", "noscript"}
        self._current_skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle start tags."""
        if tag in self._skip_tags:
            self._current_skip = True

    def handle_endtag(self, tag: str) -> None:
        """Handle end tags."""
        if tag in self._skip_tags:
            self._current_skip = False

    def handle_data(self, data: str) -> None:
        """Handle text data."""
        if not self._current_skip:
            text = data.strip()
            if text:
                self.text_parts.append(text)

    def get_text(self) -> str:
        """Get extracted text."""
        return "\n".join(self.text_parts)


class CEKDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch CEK power outage data."""

    def __init__(
        self,
        hass: HomeAssistant,
        queue: str = DEFAULT_QUEUE,
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        self.queue = queue
        self._update_interval_minutes = update_interval

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=update_interval),
        )

    def set_update_interval(self, minutes: int) -> None:
        """Update the polling interval."""
        self._update_interval_minutes = minutes
        self.update_interval = timedelta(minutes=minutes)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from CEK website."""
        try:
            return await self.hass.async_add_executor_job(self._fetch_data)
        except Exception as err:
            raise UpdateFailed(f"Error fetching CEK data: {err}") from err

    def _fetch_data(self) -> dict[str, Any]:
        """Fetch and parse CEK page (runs in executor)."""
        html = self._fetch_page(CEK_URL)
        text = self._extract_text_from_html(html)

        announcement = self._find_announcement(text)
        schedule = self._extract_queue_schedule(html, self.queue)
        date_str = self._extract_ukrainian_date(text) if announcement else None

        # Calculate next outage time
        next_outage = self._calculate_next_outage(schedule, date_str)
        is_active = self._is_outage_active(schedule)

        return {
            "date": date_str,
            "full_announcement": announcement,
            "queue": self.queue,
            "schedule": schedule,
            "next_outage": next_outage,
            "is_active": is_active,
        }

    @staticmethod
    def _fetch_page(url: str) -> str:
        """Fetch the HTML content from the given URL."""
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")

    @staticmethod
    def _extract_text_from_html(html: str) -> str:
        """Extract plain text from HTML."""
        parser = TextExtractor()
        parser.feed(html)
        return parser.get_text()

    @staticmethod
    def _extract_ukrainian_date(text: str) -> str | None:
        """Extract Ukrainian date from the announcement."""
        months_pattern = "|".join(UKRAINIAN_MONTHS)
        key_phrase = "застосовуватимуться відключення"

        for line in text.split("\n"):
            if key_phrase in line:
                match = re.search(
                    rf"(\d{{1,2}})\s+({months_pattern})", line, re.IGNORECASE
                )
                if match:
                    return f"{match.group(1)} {match.group(2)}"
        return None

    @staticmethod
    def _find_announcement(text: str) -> str | None:
        """Find the announcement sentence."""
        key_phrase = "застосовуватимуться відключення наступних черг"

        for line in text.split("\n"):
            line = line.strip()
            if key_phrase in line:
                return line
        return None

    @staticmethod
    def _extract_queue_schedule(html: str, queue: str) -> list[str]:
        """Extract time ranges for a specific queue."""
        queue_escaped = re.escape(queue)
        pattern = rf"<p>[^<]*{queue_escaped}\s*черга[^<]*(?:<br\s*/?>.*?)*</p>"

        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            p_content = match.group(0)
            time_ranges = re.findall(r"(\d{2}:\d{2})\s*до\s*(\d{2}:\d{2})", p_content)
            return [f"{start} до {end}" for start, end in time_ranges]
        return []

    def _calculate_next_outage(
        self, schedule: list[str], date_str: str | None
    ) -> datetime | None:
        """Calculate the next outage start time."""
        if not schedule or not date_str:
            return None

        try:
            # Parse the Ukrainian date
            day_match = re.match(r"(\d{1,2})", date_str)
            if not day_match:
                return None

            day = int(day_match.group(1))
            now = datetime.now()

            # Determine month from Ukrainian month name
            month = None
            for idx, month_name in enumerate(UKRAINIAN_MONTHS[:12]):
                if month_name.lower() in date_str.lower():
                    month = idx + 1
                    break

            if month is None:
                return None

            # Construct the date
            year = now.year
            if month < now.month:
                year += 1

            outage_date = datetime(year, month, day)

            # Find the next outage time
            for time_range in schedule:
                match = re.match(r"(\d{2}):(\d{2})", time_range)
                if match:
                    hour, minute = int(match.group(1)), int(match.group(2))
                    outage_time = outage_date.replace(hour=hour, minute=minute)
                    if outage_time > now:
                        return outage_time

            return None
        except (ValueError, AttributeError):
            return None

    def _is_outage_active(self, schedule: list[str]) -> bool:
        """Check if currently in an outage window."""
        if not schedule:
            return False

        now = datetime.now()
        current_time = now.strftime("%H:%M")

        for time_range in schedule:
            match = re.match(r"(\d{2}:\d{2})\s*до\s*(\d{2}:\d{2})", time_range)
            if match:
                start, end = match.group(1), match.group(2)
                if start <= current_time <= end:
                    return True
        return False

