#!/usr/bin/env python3
"""
Script to parse power outage schedule from CEK (Центральна Енергетична Компанія)
Extracts the date and schedule from announcements about scheduled disconnections.
Also detects schedule updates ("зміни в ГПВ") and merges them.

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


UKRAINIAN_MONTHS = [
    "СІЧНЯ", "ЛЮТОГО", "БЕРЕЗНЯ", "КВІТНЯ", "ТРАВНЯ", "ЧЕРВНЯ",
    "ЛИПНЯ", "СЕРПНЯ", "ВЕРЕСНЯ", "ЖОВТНЯ", "ЛИСТОПАДА", "ГРУДНЯ",
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]


def extract_ukrainian_date(text: str, key_phrase: str = "застосовуватимуться відключення") -> str | None:
    """Extract Ukrainian date from the announcement sentence."""
    months_pattern = "|".join(UKRAINIAN_MONTHS)
    
    for line in text.split("\n"):
        if key_phrase in line:
            match = re.search(rf"(\d{{1,2}})\s+({months_pattern})", line, re.IGNORECASE)
            if match:
                return f"{match.group(1)} {match.group(2)}"
    
    return None


def find_announcement(text: str) -> str | None:
    """Find the main announcement sentence."""
    key_phrase = "застосовуватимуться відключення наступних черг"
    
    for line in text.split("\n"):
        line = line.strip()
        if key_phrase in line:
            return line
    
    return None


def find_update_announcement(text: str) -> str | None:
    """Find the update announcement sentence (зміни в ГПВ)."""
    # Look for various forms of update announcements
    update_phrases = [
        "Повідомляємо про зміни в ГПВ",
        "зміни в ГПВ",
        "зміни в графіку",
        "ЗМІНИ В ГПВ",
    ]
    
    for line in text.split("\n"):
        line_stripped = line.strip()
        for phrase in update_phrases:
            if phrase.lower() in line_stripped.lower():
                return line_stripped
    
    return None


def extract_time_ranges(content: str) -> list[str]:
    """
    Extract time ranges from content.
    Handles both "до" and "по" formats.
    Returns normalized format: "HH:MM до HH:MM"
    """
    # Match both "з HH:MM до HH:MM" and "з HH:MM по HH:MM"
    time_ranges = re.findall(r"(\d{2}:\d{2})\s*(?:до|по)\s*(\d{2}:\d{2})", content)
    return [f"{start} до {end}" for start, end in time_ranges]


def extract_queue_schedule(html: str, queue: str) -> list[str]:
    """
    Extract time ranges for a specific queue from raw HTML.
    Returns list of time ranges like ["00:00 до 02:00", "05:30 до 12:30"]
    """
    queue_escaped = re.escape(queue)
    pattern = rf"<p>[^<]*{queue_escaped}\s*черга[^<]*(?:<br\s*/?>.*?)*</p>"
    
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if match:
        p_content = match.group(0)
        return extract_time_ranges(p_content)
    
    return []


def extract_update_schedule(html: str, queue: str) -> list[str] | None:
    """
    Extract schedule from the "зміни в ГПВ" (update) section.
    This section uses a different format: "📌 6.2" without "черга" and "по" instead of "до".
    Returns None if no update section found.
    """
    # Find the "зміни в ГПВ" section
    update_match = re.search(r'зміни в ГПВ.*?(?=<p>📢|<p>&nbsp;</p>\s*<p>📢|$)', html, re.IGNORECASE | re.DOTALL)
    
    if not update_match:
        return None
    
    update_section = update_match.group(0)
    
    # Find the queue in the update section
    # Format: "📌 6.2<br />✔️ з 00:00 по 02:00..."
    queue_escaped = re.escape(queue)
    # Pattern: queue number followed by times until next queue or end
    queue_pattern = rf"📌\s*{queue_escaped}(?:\s*черга)?[^📌]*"
    
    queue_match = re.search(queue_pattern, update_section, re.IGNORECASE | re.DOTALL)
    
    if queue_match:
        queue_content = queue_match.group(0)
        return extract_time_ranges(queue_content)
    
    return None


def extract_all_queue_schedules(html: str, queue: str) -> list[list[str]]:
    """
    Extract ALL schedule blocks for a specific queue from raw HTML.
    Returns list of schedules (each schedule is a list of time ranges).
    This helps identify main schedule vs updates.
    """
    queue_escaped = re.escape(queue)
    pattern = rf"<p>[^<]*{queue_escaped}\s*черга[^<]*(?:<br\s*/?>.*?)*</p>"
    
    schedules = []
    for match in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
        p_content = match.group(0)
        time_ranges = extract_time_ranges(p_content)
        if time_ranges:
            schedules.append(time_ranges)
    
    return schedules


def merge_schedules(original: list[str], update: list[str]) -> list[str]:
    """
    Merge original schedule with update.
    The update schedule typically replaces the original for the same date.
    """
    if not update:
        return original
    # For now, the update replaces the original entirely
    # If more complex merging is needed, we can enhance this
    return update


def parse_cek_page(url: str, queue: str = "6.2") -> dict:
    """
    Parse the CEK page and extract disconnection date and schedule.
    Also detects and handles schedule updates.
    
    Args:
        url: The URL to parse
        queue: The queue number to get schedule for (e.g., "6.2")
    
    Returns a dictionary with the extracted data.
    """
    html = fetch_page(url)
    text = extract_text_from_html(html)
    
    # Find main announcement
    announcement = find_announcement(text)
    date_str = extract_ukrainian_date(text) if announcement else None
    
    # Find update announcement
    update_announcement = find_update_announcement(text)
    has_update = update_announcement is not None
    
    # Get main schedule (from "X.X черга:" format)
    main_schedule = extract_queue_schedule(html, queue)
    
    # Get update schedule (from "зміни в ГПВ" section)
    update_schedule = extract_update_schedule(html, queue)
    
    print(f"\n🔍 Debug: Main schedule for queue {queue}: {main_schedule}")
    print(f"🔍 Debug: Update schedule for queue {queue}: {update_schedule}")
    print(f"🔍 Debug: Has update announcement: {has_update}")
    
    # Determine the final schedule
    # If there's an update schedule, use it; otherwise use main schedule
    if update_schedule:
        schedule = update_schedule
        has_update = True
        print(f"\n⚠️  Using UPDATE schedule!")
    else:
        schedule = main_schedule
        print(f"\n✅ Using MAIN schedule (no update found)")
    
    return {
        "date": date_str,
        "full_announcement": announcement,
        "queue": queue,
        "schedule": schedule,
        "has_update": has_update,
        "update_announcement": update_announcement,
        "main_schedule": main_schedule,  # For debugging
        "update_schedule": update_schedule,  # For debugging
    }


def debug_page_structure(html: str, text: str, queue: str):
    """Debug: Print detailed page structure info."""
    print("\n" + "=" * 60)
    print("DEBUG: PAGE STRUCTURE ANALYSIS")
    print("=" * 60)
    
    # Find all <p> tags containing the queue
    queue_escaped = re.escape(queue)
    pattern = rf"<p>[^<]*{queue_escaped}\s*черга[^<]*(?:<br\s*/?>.*?)*</p>"
    
    print(f"\n📋 Looking for pattern: {pattern[:50]}...")
    
    matches = list(re.finditer(pattern, html, re.IGNORECASE | re.DOTALL))
    print(f"\n📋 Found {len(matches)} <p> blocks with queue {queue}:")
    
    for i, match in enumerate(matches):
        content = match.group(0)
        # Find position in HTML to understand context
        start_pos = match.start()
        # Get 200 chars before to see context
        context_before = html[max(0, start_pos-200):start_pos]
        
        print(f"\n--- Block {i+1} ---")
        print(f"Position: {start_pos}")
        print(f"Context before (last 100 chars): ...{context_before[-100:]}")
        print(f"Content: {content[:200]}...")
        
        # Extract times
        times = re.findall(r"(\d{2}:\d{2})\s*до\s*(\d{2}:\d{2})", content)
        print(f"Times found: {times}")
    
    # Also search for "зміни" sections
    print("\n" + "-" * 40)
    print("📋 Looking for 'зміни' (changes) sections in text:")
    
    for i, line in enumerate(text.split("\n")):
        if "зміни" in line.lower() or "ГПВ" in line:
            print(f"   Line {i}: {line[:100]}...")
    
    # Search for queue mentions near "зміни"
    print("\n" + "-" * 40)
    print(f"📋 Looking for queue {queue} mentions near 'зміни':")
    
    # Find all occurrences of the queue in the HTML
    queue_pattern = rf"{queue_escaped}\s*черга"
    for match in re.finditer(queue_pattern, html, re.IGNORECASE):
        pos = match.start()
        context = html[max(0, pos-150):pos+150]
        if "зміни" in context.lower() or "змін" in context.lower():
            print(f"\n   Found near 'зміни' at position {pos}:")
            print(f"   {context[:100]}...")


def main():
    url = "https://cek.dp.ua/index.php/cpojivaham/vidkliuchennia.html"
    queue = "6.2"
    
    print(f"Fetching data from: {url}")
    print(f"Queue: {queue}")
    print("=" * 60)
    
    try:
        # Fetch page first for debugging
        html = fetch_page(url)
        text = extract_text_from_html(html)
        
        # Debug page structure
        debug_page_structure(html, text, queue)
        
        result = parse_cek_page(url, queue)
        
        print("\n" + "=" * 60)
        print("RESULTS:")
        print("=" * 60)
        
        if result["date"]:
            print(f"\n📅 Date: {result['date']}")
        else:
            print("\n❌ Could not extract date")
        
        if result["has_update"]:
            print(f"\n⚠️  SCHEDULE UPDATE DETECTED!")
            print(f"   Update announcement: {result['update_announcement']}")
        
        if result["schedule"]:
            print(f"\n⚡ Schedule for {result['queue']} черга:")
            for time_range in result["schedule"]:
                print(f"   {time_range}")
            
            # Calculate hours
            total_minutes = 0
            for tr in result["schedule"]:
                match = re.match(r"(\d{2}):(\d{2})\s*до\s*(\d{2}):(\d{2})", tr)
                if match:
                    start_h, start_m = int(match.group(1)), int(match.group(2))
                    end_h, end_m = int(match.group(3)), int(match.group(4))
                    total_minutes += (end_h * 60 + end_m) - (start_h * 60 + start_m)
            
            hours = total_minutes / 60
            percentage = (total_minutes / 1440) * 100
            print(f"\n📊 Total outage: {hours:.1f} hours ({percentage:.1f}% of day)")
        else:
            print(f"\n❌ No schedule found for {queue} черга")
        
        if result["full_announcement"]:
            print(f"\n📢 Main Announcement:")
            print(f"   {result['full_announcement'][:100]}...")
        
        return result
        
    except urllib.error.URLError as e:
        print(f"❌ Error fetching page: {e}")
        return None
    except Exception as e:
        print(f"❌ Error parsing page: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    main()
