"""Data update coordinator for CEK Power Outage."""
from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
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

# Queue header line: "🔹 Черга 6.2", "📌 6.2", "6.2 черга"
QUEUE_LINE_RE = re.compile(r"(?<![\d.:])(\d{1,2}\.\d{1,2})(?![\d.:])")


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

        now = dt_util.now()
        blocks = self._parse_announcements(text, self.queue)
        days = self._build_days(blocks, now.date())

        # Single-day fields describe today if published, otherwise the nearest
        # upcoming day; "days" holds every published day from today on.
        current = days[0] if days else None
        today_schedule = (
            current["schedule"]
            if current and current["date"] == now.date().isoformat()
            else []
        )

        _LOGGER.debug(
            "Found %d announcements, %d days for queue %s",
            len(blocks),
            len(days),
            self.queue,
        )

        return {
            "date": current["date_label"] if current else None,
            "full_announcement": current["announcement"] if current else None,
            "queue": self.queue,
            "schedule": current["schedule"] if current else [],
            "next_outage": self._calculate_next_outage(days, now),
            "is_active": self._is_outage_active(today_schedule, now),
            "has_update": current["has_update"] if current else False,
            "update_announcement": current["update_announcement"] if current else None,
            "days": days,
        }

    @staticmethod
    def _fetch_page(url: str) -> str:
        """Fetch the HTML content from the given URL with retries for transient errors."""
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "uk,en;q=0.9",
            },
        )
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=25) as response:
                    return response.read().decode("utf-8")
            except (OSError, urllib.error.URLError) as err:
                last_error = err
                # Errno -3 (EAI_AGAIN) = temporary DNS failure, try again
                if getattr(err, "errno", None) == -3 or "Try again" in str(err):
                    if attempt < 2:
                        _LOGGER.warning(
                            "CEK fetch attempt %d/3 failed (DNS/network), retrying in 5s: %s",
                            attempt + 1,
                            err,
                        )
                        time.sleep(5)
                    else:
                        raise
                else:
                    raise
        if last_error is not None:
            raise last_error

    @staticmethod
    def _extract_text_from_html(html: str) -> str:
        """Extract plain text from HTML."""
        parser = TextExtractor()
        parser.feed(html)
        return parser.get_text()

    @staticmethod
    def _parse_ranges(content: str) -> list[tuple[int, int]]:
        """
        Extract time ranges as (start, end) minutes of the day.
        Handles "до", "по", and dash "-" formats.
        """
        return [
            (int(sh) * 60 + int(sm), int(eh) * 60 + int(em))
            for sh, sm, eh, em in re.findall(
                r"(\d{1,2}):(\d{2})\s*(?:до|по|-|–|—)\s*(\d{1,2}):(\d{2})", content
            )
        ]

    @staticmethod
    def _format_ranges(ranges: list[tuple[int, int]]) -> list[str]:
        """Format minute ranges as "HH:MM до HH:MM"."""
        return [
            f"{start // 60:02d}:{start % 60:02d} до {end // 60:02d}:{end % 60:02d}"
            for start, end in ranges
        ]

    @staticmethod
    def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Sort ranges and join overlapping or adjacent ones."""
        merged: list[tuple[int, int]] = []
        for start, end in sorted(r for r in ranges if r[1] > r[0]):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    @staticmethod
    def _subtract_window(
        ranges: list[tuple[int, int]], window: tuple[int, int]
    ) -> list[tuple[int, int]]:
        """Remove the part of each range that falls inside the window."""
        win_start, win_end = window
        result: list[tuple[int, int]] = []
        for start, end in ranges:
            if start < win_start:
                result.append((start, min(end, win_start)))
            if end > win_end:
                result.append((max(start, win_end), end))
        return result

    @classmethod
    def _extract_queue_ranges(
        cls, lines: list[str], queue: str
    ) -> list[tuple[int, int]] | None:
        """
        Extract time ranges for a queue from the lines of one announcement.
        Handles formats like:
        - "🔹 Черга 6.2" followed by "10:00-14:00" lines
        - "📌 6.2" followed by "✔️ з 00:00 по 02:00" lines
        - "6.2 черга: 06:00 до 09:30, 16:30 до 20:00"
        Returns None if the queue is not mentioned.
        """
        ranges: list[tuple[int, int]] | None = None
        collecting = False
        for line in lines:
            match = QUEUE_LINE_RE.search(line)
            if match and ("черга" in line.lower() or line.startswith(("🔹", "📌"))):
                collecting = match.group(1) == queue
                if collecting:
                    ranges = (ranges or []) + cls._parse_ranges(line[match.end():])
                continue
            if collecting:
                found = cls._parse_ranges(line)
                if not found:
                    collecting = False
                else:
                    ranges = (ranges or []) + found
        return ranges

    @classmethod
    def _parse_announcements(cls, text: str, queue: str) -> list[dict[str, Any]]:
        """
        Split the page into dated schedule announcements (page order, newest first).

        Main announcements ("застосовуватимуться відключення") set the day's
        schedule; updates ("зміни в/у ГПВ") change it, optionally only within
        the "з HH:MM до HH:MM" window given in their header.
        """
        months_pattern = "|".join(UKRAINIAN_MONTHS)
        announcements = []

        for chunk in text.split("📢")[1:]:
            lines = [line.strip() for line in chunk.split("\n") if line.strip()]

            # Header runs until the first queue line
            header_lines = []
            for line in lines:
                if QUEUE_LINE_RE.search(line) and (
                    "черга" in line.lower() or line.startswith(("🔹", "📌"))
                ):
                    break
                header_lines.append(line)
            header = " ".join(header_lines)
            header_lower = header.lower()

            is_update = "зміни" in header_lower and "гпв" in header_lower
            if not is_update and "застосовуватимуться відключення" not in header_lower:
                continue

            date_match = re.search(
                rf"(\d{{1,2}})\s+({months_pattern})", header, re.IGNORECASE
            )
            if not date_match:
                continue

            window = None
            if is_update:
                window_ranges = cls._parse_ranges(header)
                if window_ranges:
                    window = window_ranges[0]

            announcements.append({
                "day": int(date_match.group(1)),
                "month": UKRAINIAN_MONTHS.index(date_match.group(2).upper()) + 1,
                "date_label": f"{date_match.group(1)} {date_match.group(2)}",
                "header": header,
                "is_update": is_update,
                "window": window,
                "ranges": cls._extract_queue_ranges(lines[len(header_lines):], queue),
            })

        return announcements

    @staticmethod
    def _resolve_date(day: int, month: int, today: date) -> date | None:
        """Pick the year that puts day/month closest to today."""
        candidates = []
        for year in (today.year - 1, today.year, today.year + 1):
            try:
                candidates.append(date(year, month, day))
            except ValueError:
                continue
        return min(candidates, key=lambda d: abs(d - today), default=None)

    @classmethod
    def _build_days(
        cls, announcements: list[dict[str, Any]], today: date
    ) -> list[dict[str, Any]]:
        """Apply announcements oldest to newest and return one entry per day."""
        days: dict[date, dict[str, Any]] = {}

        for item in reversed(announcements):
            day_date = cls._resolve_date(item["day"], item["month"], today)
            if day_date is None or day_date < today:
                continue

            day = days.setdefault(day_date, {
                "date_label": item["date_label"],
                "announcement": None,
                "update_announcement": None,
                "has_update": False,
                "ranges": [],
            })
            ranges = item["ranges"]

            if not item["is_update"]:
                # A (re)issued main schedule replaces everything before it
                day["ranges"] = ranges or []
                day["announcement"] = item["header"]
                day["has_update"] = False
                day["update_announcement"] = None
            else:
                day["has_update"] = True
                day["update_announcement"] = item["header"]
                if item["window"]:
                    # Queue not listed in a windowed update => no outages in that window
                    day["ranges"] = cls._subtract_window(
                        day["ranges"], item["window"]
                    ) + (ranges or [])
                elif ranges is not None:
                    day["ranges"] = ranges

            day["ranges"] = cls._merge_ranges(day["ranges"])

        result = []
        for day_date in sorted(days):
            day = days.pop(day_date)
            ranges = day.pop("ranges")
            result.append({
                "date": day_date.isoformat(),
                **day,
                "schedule": cls._format_ranges(ranges),
                "outage_hours": round(sum(end - start for start, end in ranges) / 60, 1),
            })
        return result

    def _calculate_next_outage(
        self, days: list[dict[str, Any]], now: datetime
    ) -> datetime | None:
        """Calculate the next outage start time (timezone-aware) across all days."""
        local_tz = dt_util.get_default_time_zone()
        for day in days:
            day_date = date.fromisoformat(day["date"])
            for start, _ in self._parse_ranges(", ".join(day["schedule"])):
                outage_time = datetime(
                    day_date.year, day_date.month, day_date.day, tzinfo=local_tz
                ) + timedelta(minutes=start)
                if outage_time > now:
                    return outage_time
        return None

    def _is_outage_active(self, schedule: list[str], now: datetime) -> bool:
        """Check if currently in an outage window of today's schedule."""
        current = now.hour * 60 + now.minute
        return any(
            start <= current < end
            for start, end in self._parse_ranges(", ".join(schedule))
        )
