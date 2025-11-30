from __future__ import annotations
import re
from datetime import datetime, timedelta
from typing import List, Optional
import requests
from bs4 import BeautifulSoup

from ..base import BaseProvider
from ..models import Event, Stream
from .utils.logos import get_team_logo  # NUEVO

class TiroalpaloProvider(BaseProvider):
    name = "Tiroalpalo"
    LIST_URL = "https://tiroalpalome.com/directo"

    def fetch_events(self) -> List[Event]:
        events = []
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            html = requests.get(self.LIST_URL, timeout=15, headers=headers).text
        except Exception as e:
            print(f"[Tiroalpalo] Error descargando lista: {e}")
            return events

        soup = BeautifulSoup(html, "html.parser")

        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if not href.startswith("http"):
                if href.startswith("/"):
                    href = f"https://tiroalpalome.com{href}"
                else:
                    href = f"https://tiroalpalome.com/{href}"

            if "tiroalpalome.com" in href and ("-" in text or " vs " in text.lower()):
                links.append((href, text))

        seen = set()
        for href, text in links:
            if href in seen:
                continue
            seen.add(href)

            try:
                event = self._parse_event_page(href, text)
                if event:
                    events.append(event)
            except Exception as e:
                print(f"[Tiroalpalo] Error parseando {href}: {e}")
                continue

        return events

    def _parse_event_page(self, url: str, fallback: str) -> Optional[Event]:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            html = requests.get(url, timeout=15, headers=headers).text
        except Exception as e:
            print(f"[Tiroalpalo] Error descargando página: {e}")
            return None

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find(["h1", "h2", "h3"])
        title = title_tag.get_text(strip=True) if title_tag else fallback

        match_time = None
        home = ""
        away = ""

        m = re.match(r"(\d{1,2}:\d{2})\s*[|\-]?(.*)", title)
        if m:
            match_time = m.group(1)
            title_no_time = m.group(2).strip()
        else:
            title_no_time = title

        if " vs " in title_no_time.lower():
            parts = re.split(r"\s+vs\s+", title_no_time, flags=re.IGNORECASE)
            if len(parts) == 2:
                home, away = parts[0].strip(), parts[1].strip()
        elif "-" in title_no_time:
            parts = title_no_time.split("-", 1)
            if len(parts) == 2:
                home, away = parts[0].strip(), parts[1].strip()
        else:
            home = title_no_time

        start_ms = 0
        if match_time:
            try:
                hh, mm = map(int, match_time.split(":"))
                now = datetime.utcnow()
                dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if dt < now:
                    dt += timedelta(days=1)
                start_ms = int(dt.timestamp() * 1000)
            except Exception as e:
                print(f"[Tiroalpalo] Error convirtiendo hora: {e}")

        streams = []
        for iframe in soup.find_all("iframe", src=True):
            src = iframe.get("src")
            if src and ("stream" in src.lower() or "embed" in src.lower()):
                streams.append(Stream(
                    name=f"Stream {len(streams) + 1}",
                    url=src,
                    source="Tiroalpalo"
                ))

        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            if any(keyword in text for keyword in ["link", "alternativo", "stream", "ver", "canal"]):
                href = a["href"]
                if not href.startswith("http"):
                    continue
                streams.append(Stream(
                    name=a.get_text(strip=True),
                    url=href,
                    source="Tiroalpalo"
                ))

        if not streams:
            return None

        return Event(
            id=url,
            name=title_no_time if title_no_time else f"{home} vs {away}",
            url=url,
            league="Tiroalpalo",
            home=home,
            away=away,
            start_time=start_ms,
            provider="Tiroalpalo",
            streams=streams,
            match_time=match_time or "",
            home_logo=get_team_logo(home),
            away_logo=get_team_logo(away),
            league_logo=None
        )
