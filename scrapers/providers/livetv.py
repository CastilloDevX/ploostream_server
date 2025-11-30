from __future__ import annotations
from typing import List, Tuple
import re

import requests
from bs4 import BeautifulSoup
import urllib3

from ..base import BaseProvider
from ..models import Event, Stream
from .utils.logos import get_team_logo

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
}


class LiveTVProvider(BaseProvider):
    name = "LiveTV"
    LIST_URL = "https://livetv.sx/enx/allupcomingsports/1/"

    def fetch_events(self) -> List[Event]:
        events: List[Event] = []

        try:
            resp = requests.get(
                self.LIST_URL,
                headers=UA_HEADERS,
                timeout=20,
                verify=False,
            )
            resp.raise_for_status()
        except Exception as e:
            print("[LiveTV] Error al descargar LIST_URL:", e)
            return events

        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True, class_="bottomgray"):
            href = a["href"]
            if "eventinfo" not in href:
                continue

            event_url = href if href.startswith("http") else f"https://livetv.sx{href}"
            title = " ".join(a.stripped_strings)
            home, away = self._split_teams(title)

            evdesc = a.find_next("span", class_="evdesc")
            raw_desc = evdesc.get_text(" ", strip=True) if evdesc else ""
            league = re.search(r"\((.*?)\)", raw_desc)
            league = league.group(1).strip() if league else "LiveTV"

            event = Event(
                id=event_url,
                name=f"{home} vs {away}",
                url=event_url,
                league=league,
                home=home,
                away=away,
                start_time=0,
                provider=self.name,
                streams=[],
                home_logo=get_team_logo(home),
                away_logo=get_team_logo(away),
                league_logo=get_team_logo(league)
            )
            events.append(event)

        unique: List[Event] = []
        seen = set()
        for ev in events:
            if ev.url in seen:
                continue
            seen.add(ev.url)
            unique.append(ev)

        return unique

    def load_streams(self, event_url: str) -> List[Stream]:
        return self._parse_event_streams(event_url)

    def _split_teams(self, title: str) -> Tuple[str, str]:
        for sep in [" – ", " - ", " vs ", " Vs ", " v "]:
            if sep in title:
                h, a = title.split(sep, 1)
                return h.strip(), a.strip()
        return title.strip(), ""

    def _absolute_from(self, base: str, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("//"):
            return "https:" + url
        m = re.match(r"(https?://[^/]+)", base)
        root = m.group(1) if m else "https://livetv.sx"
        if url.startswith("/"):
            return root + url
        return root + "/" + url.lstrip("/")

    def _parse_event_streams(self, event_url: str) -> List[Stream]:
        streams: List[Stream] = []

        try:
            resp = requests.get(
                event_url,
                headers=UA_HEADERS,
                timeout=20,
                verify=False,
            )
            resp.raise_for_status()
        except Exception as e:
            print("[LiveTV] Error al descargar eventinfo:", e)
            return streams

        soup = BeautifulSoup(resp.text, "html.parser")
        webplayer_urls = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "webplayer.php" in href:
                webplayer_urls.add(self._absolute_from(event_url, href))

        for script in soup.find_all("script"):
            txt = script.string or ""
            for m in re.findall(r"(https?://[^'\" ]*webplayer\.php[^'\" ]*)", txt):
                webplayer_urls.add(m)

        if not webplayer_urls:
            for iframe in soup.find_all("iframe", src=True):
                src = iframe["src"]
                full = self._absolute_from(event_url, src)
                streams.append(Stream(
                    name="Stream 1",
                    url=full,
                    source=self.name,
                    language=None,
                ))
            return streams

        for idx, wp_url in enumerate(sorted(webplayer_urls), start=1):
            try:
                wp_resp = requests.get(
                    wp_url,
                    headers=UA_HEADERS,
                    timeout=20,
                    verify=False,
                )
                wp_resp.raise_for_status()
            except Exception as e:
                print("[LiveTV] Error al descargar webplayer:", e)
                continue

            wp_soup = BeautifulSoup(wp_resp.text, "html.parser")
            iframe = wp_soup.find("iframe", src=True)
            if not iframe:
                continue

            src = iframe["src"]
            full = self._absolute_from(wp_url, src)

            streams.append(Stream(
                name=f"Stream {idx}",
                url=full,
                source=self.name,
                language=None,
            ))

        return streams
