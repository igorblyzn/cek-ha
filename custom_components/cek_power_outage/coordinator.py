"""Data update coordinator for CEK Power Outage."""
from __future__ import annotations

import logging
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
        self._last_successful_data: dict[str, Any] | None = None
        self._last_updated: datetime | None = None
        self._last_check: datetime | None = None
        self._last_error: str | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=update_interval),
        )

    @property
    def last_updated(self) -> datetime | None:
        """Return the last successful update timestamp."""
        return self._last_updated

    @property
    def last_check(self) -> datetime | None:
        """Return the last fetch attempt timestamp (success or failure)."""
        return self._last_check

    @property
    def last_error(self) -> str | None:
        """Return the last error message, if any."""
        return self._last_error

    def set_update_interval(self, minutes: int) -> None:
        """Update the polling interval."""
        self._update_interval_minutes = minutes
        self.update_interval = timedelta(minutes=minutes)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from CEK website."""
        # Track every fetch attempt
        self._last_check = datetime.now()

        try:
            data = await self.hass.async_add_executor_job(self._fetch_data)
            # Success - cache the data and clear error
            self._last_successful_data = data
            self._last_updated = datetime.now()
            self._last_error = None
            return data
        except Exception as err:
            error_msg = f"Error fetching CEK data: {err}"
            self._last_error = error_msg
            _LOGGER.warning(error_msg)

            # Return cached data if available
            if self._last_successful_data is not None:
                _LOGGER.info("Using cached data from %s", self._last_updated)
                return self._last_successful_data

            # No cached data - raise the error
            raise UpdateFailed(error_msg) from err

    def _fetch_data(self) -> dict[str, Any]:
        """Fetch and parse CEK page (runs in executor)."""
        html = self._fetch_page(CEK_URL)
        text = self._extract_text_from_html(html)

        # Get the first (most relevant) schedule block with its date
        schedule_data = self._extract_first_schedule_block(html, text, self.queue)

        date_str = schedule_data.get("date")
        main_schedule = schedule_data.get("schedule", [])
        announcement = schedule_data.get("announcement")

        # Check for schedule updates ("зміни в ГПВ")
        update_announcement = self._find_update_announcement(text)
        update_schedule = self._extract_update_schedule(html, self.queue)

        # Use update schedule if available, otherwise use main schedule
        if update_schedule:
            schedule = update_schedule
            has_update = True
            _LOGGER.debug("Using update schedule for queue %s", self.queue)
        else:
            schedule = main_schedule
            has_update = update_announcement is not None
            _LOGGER.debug("Using main schedule for queue %s", self.queue)

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
            "has_update": has_update,
            "update_announcement": update_announcement,
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

    def _extract_first_schedule_block(
        self, html: str, text: str, queue: str
    ) -> dict[str, Any]:
        """
        Extract the first schedule block with its associated date.

        The page may contain multiple schedule announcements (e.g., today and tomorrow).
        This method finds the first one and returns the date and schedule together.
        """
        months_pattern = "|".join(UKRAINIAN_MONTHS)
        key_phrase = "застосовуватимуться відключення"
        queue_escaped = re.escape(queue)

        # Find all announcement lines with dates
        announcements = []
        for line in text.split("\n"):
            if key_phrase in line:
                date_match = re.search(
                    rf"(\d{{1,2}})\s+({months_pattern})", line, re.IGNORECASE
                )
                if date_match:
                    announcements.append({
                        "line": line.strip(),
                        "date": f"{date_match.group(1)} {date_match.group(2)}",
                    })

        # Find all schedule blocks for this queue
        queue_pattern = rf"<p>[^<]*{queue_escaped}\s*черга[^<]*(?:<br\s*/?>.*?)*</p>"
        schedule_matches = list(re.finditer(queue_pattern, html, re.IGNORECASE | re.DOTALL))

        schedules = []
        for match in schedule_matches:
            p_content = match.group(0)
            time_ranges = re.findall(r"(\d{2}:\d{2})\s*до\s*(\d{2}:\d{2})", p_content)
            if time_ranges:
                schedules.append([f"{start} до {end}" for start, end in time_ranges])

        # Return the first schedule with its corresponding date
        # Assume announcements and schedules are in the same order on the page
        result: dict[str, Any] = {
            "date": None,
            "announcement": None,
            "schedule": [],
        }

        if announcements:
            result["date"] = announcements[0]["date"]
            result["announcement"] = announcements[0]["line"]

        if schedules:
            result["schedule"] = schedules[0]

        _LOGGER.debug(
            "Found %d announcements and %d schedule blocks. Using first.",
            len(announcements),
            len(schedules),
        )

        return result

    @staticmethod
    def _find_update_announcement(text: str) -> str | None:
        """Find the update announcement sentence (зміни в ГПВ)."""
        update_phrases = [
            "Повідомляємо про зміни в ГПВ",
            "зміни в ГПВ",
            "ЗМІНИ В ГПВ",
        ]

        for line in text.split("\n"):
            line_stripped = line.strip()
            for phrase in update_phrases:
                if phrase.lower() in line_stripped.lower():
                    return line_stripped
        return None

    @staticmethod
    def _extract_time_ranges(content: str) -> list[str]:
        """
        Extract time ranges from content.
        Handles both "до" and "по" formats.
        Returns normalized format: "HH:MM до HH:MM"
        """
        time_ranges = re.findall(r"(\d{2}:\d{2})\s*(?:до|по)\s*(\d{2}:\d{2})", content)
        return [f"{start} до {end}" for start, end in time_ranges]

    def _extract_update_schedule(self, html: str, queue: str) -> list[str] | None:
        """
        Extract schedule from the "зміни в ГПВ" (update) section.
        This section uses a different format: "📌 6.2" without "черга" and "по" instead of "до".
        Returns None if no update section found.
        """
        # Find the "зміни в ГПВ" section
        update_match = re.search(
            r'зміни в ГПВ.*?(?=<p>📢|<p>&nbsp;</p>\s*<p>📢|$)',
            html,
            re.IGNORECASE | re.DOTALL
        )

        if not update_match:
            return None

        update_section = update_match.group(0)

        # Find the queue in the update section
        # Format: "📌 6.2<br />✔️ з 00:00 по 02:00..."
        queue_escaped = re.escape(queue)
        queue_pattern = rf"📌\s*{queue_escaped}(?:\s*черга)?[^📌]*"

        queue_match = re.search(queue_pattern, update_section, re.IGNORECASE | re.DOTALL)

        if queue_match:
            queue_content = queue_match.group(0)
            return self._extract_time_ranges(queue_content)

        return None

    @staticmethod
    def _extract_ukrainian_date(text: str) -> str | None:
        """Extract Ukrainian date from the announcement (legacy, kept for compatibility)."""
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
        """Find the announcement sentence (legacy, kept for compatibility)."""
        key_phrase = "застосовуватимуться відключення наступних черг"

        for line in text.split("\n"):
            line = line.strip()
            if key_phrase in line:
                return line
        return None

    @staticmethod
    def _extract_queue_schedule(html: str, queue: str) -> list[str]:
        """Extract time ranges for a specific queue (legacy, kept for compatibility)."""
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
        """Calculate the next outage start time (timezone-aware)."""
        if not schedule or not date_str:
            return None

        try:
            # Parse the Ukrainian date
            day_match = re.match(r"(\d{1,2})", date_str)
            if not day_match:
                return None

            day = int(day_match.group(1))
            now = dt_util.now()  # Use HA's timezone-aware now

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

            # Create timezone-aware datetime using HA's timezone
            local_tz = dt_util.get_default_time_zone()
            outage_date = datetime(year, month, day, tzinfo=local_tz)

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

