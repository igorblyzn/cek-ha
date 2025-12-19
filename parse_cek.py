#!/usr/bin/env python3
"""
Script to parse power outage schedule from CEK (Центральна Енергетична Компанія)
Extracts the date and schedule from announcements about scheduled disconnections.

No external dependencies - uses only Python standard library.
"""

import re
import urllib.request
from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    """Simple HTML parser that extracts text content."""
    
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._skip_tags = {"script", "style", "noscript"}
        self._current_skip = False
    
    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._current_skip = True
    
    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._current_skip = False
    
    def handle_data(self, data):
        if not self._current_skip:
            text = data.strip()
            if text:
                self.text_parts.append(text)
    
    def get_text(self) -> str:
        return "\n".join(self.text_parts)


def fetch_page(url: str) -> str:
    """Fetch the HTML content from the given URL using urllib."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def extract_text_from_html(html: str) -> str:
    """Extract plain text from HTML using built-in parser."""
    parser = TextExtractor()
    parser.feed(html)
    return parser.get_text()


def extract_ukrainian_date(text: str) -> str | None:
    """
    Extract Ukrainian date from the announcement sentence.
    Looks for pattern like "18 ГРУДНЯ" in the line with key phrase.
    """
    ukrainian_months = [
        "СІЧНЯ", "ЛЮТОГО", "БЕРЕЗНЯ", "КВІТНЯ", "ТРАВНЯ", "ЧЕРВНЯ",
        "ЛИПНЯ", "СЕРПНЯ", "ВЕРЕСНЯ", "ЖОВТНЯ", "ЛИСТОПАДА", "ГРУДНЯ",
        "січня", "лютого", "березня", "квітня", "травня", "червня",
        "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
    ]
    
    months_pattern = "|".join(ukrainian_months)
    key_phrase = "застосовуватимуться відключення"
    
    for line in text.split("\n"):
        if key_phrase in line:
            match = re.search(rf"(\d{{1,2}})\s+({months_pattern})", line, re.IGNORECASE)
            if match:
                return f"{match.group(1)} {match.group(2)}"
    
    return None


def find_announcement(text: str) -> str | None:
    """Find the announcement sentence containing the key phrase."""
    key_phrase = "застосовуватимуться відключення наступних черг"
    
    for line in text.split("\n"):
        line = line.strip()
        if key_phrase in line:
            return line
    
    return None


def extract_queue_schedule(html: str, queue: str) -> list[str]:
    """
    Extract time ranges for a specific queue (e.g., "6.2 черга") from raw HTML.
    Returns list of time ranges like ["00:00 до 02:00", "05:30 до 12:30"]
    """
    # Find the <p> element containing the queue
    # Pattern: <p>...queue черга:...time slots...</p>
    queue_escaped = re.escape(queue)
    pattern = rf"<p>[^<]*{queue_escaped}\s*черга[^<]*(?:<br\s*/?>.*?)*</p>"
    
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if match:
        p_content = match.group(0)
        # Extract all time ranges: "HH:MM до HH:MM"
        time_ranges = re.findall(r"(\d{2}:\d{2})\s*до\s*(\d{2}:\d{2})", p_content)
        return [f"{start} до {end}" for start, end in time_ranges]
    
    return []


def parse_cek_page(url: str, queue: str = "6.2") -> dict:
    """
    Parse the CEK page and extract disconnection date and schedule.
    
    Args:
        url: The URL to parse
        queue: The queue number to get schedule for (e.g., "6.2")
    
    Returns a dictionary with the extracted data.
    """
    html = fetch_page(url)
    text = extract_text_from_html(html)
    
    announcement = find_announcement(text)
    schedule = extract_queue_schedule(html, queue)  # Use raw HTML for schedule
    
    return {
        "date": extract_ukrainian_date(text) if announcement else None,
        "full_announcement": announcement,
        "queue": queue,
        "schedule": schedule,
    }


def main():
    url = "https://cek.dp.ua/index.php/cpojivaham/vidkliuchennia.html"
    queue = "6.2"
    
    print(f"Fetching data from: {url}")
    print("-" * 50)
    
    try:
        result = parse_cek_page(url, queue)
        
        if result["date"]:
            print(f"📅 Date: {result['date']}")
        else:
            print("❌ Could not extract date")
        
        if result["schedule"]:
            print(f"\n⚡ Schedule for {result['queue']} черга:")
            for time_range in result["schedule"]:
                print(f"   {time_range}")
        else:
            print(f"\n❌ No schedule found for {queue} черга")
        
        if result["full_announcement"]:
            print(f"\n📢 Announcement:")
            print(result["full_announcement"])
        
        return result
        
    except urllib.error.URLError as e:
        print(f"❌ Error fetching page: {e}")
        return None
    except Exception as e:
        print(f"❌ Error parsing page: {e}")
        return None


if __name__ == "__main__":
    main()
