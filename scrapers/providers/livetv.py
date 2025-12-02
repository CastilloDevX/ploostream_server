from __future__ import annotations
from typing import List, Tuple
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
import concurrent.futures

from ..base import BaseProvider
from ..models import Event, Stream
from .utils.logos import get_team_logo

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
}

class LiveTVProvider(BaseProvider):
    name = "LiveTV"
    LIST_URL = "https://livetv.sx/enx/allupcoming/"

    def fetch_events(self) -> List[Event]:
        events: List[Event] = []

        try:
            resp = requests.get(self.LIST_URL, headers=UA_HEADERS, timeout=20, verify=False)
            resp.raise_for_status()
        except Exception as e:
            print("[LiveTV] Error al descargar LIST_URL:", e)
            return events

        soup = BeautifulSoup(resp.text, "html.parser")
        event_data = []

        for a_tag in soup.find_all("a", class_="live", href=True):
            td_parent = a_tag.find_parent("td")
            if not td_parent:
                continue

            # Solo incluir si el evento está en vivo
            is_live = td_parent.find("img", src="//cdn.livetv869.me/img/live.gif")
            if not is_live:
                continue

            span = td_parent.find("span", class_="evdesc")
            date_text = league = ""
            if span:
                full_text = span.get_text(separator="|", strip=True)
                parts = full_text.split("|")
                date_text = parts[0].strip() if len(parts) > 0 else ""
                league = parts[1].strip(" ()") if len(parts) > 1 else ""

            event_text = a_tag.get_text(strip=True)
            for sep in [" – ", " - ", " vs ", " Vs ", " v ", "–", "-"]:
                if sep in event_text:
                    home, away = map(str.strip, event_text.split(sep, 1))
                    break
            else:
                home, away = event_text.strip(), ""

            event_url = a_tag["href"]
            if not event_url.startswith("http"):
                event_url = f"https://livetv.sx{event_url}"

            event_data.append((event_url, home, away, league, date_text))

        # Cargar streams en paralelo
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_event = {
                executor.submit(self.load_streams, url): (url, home, away, league, start_time)
                for url, home, away, league, start_time in event_data
            }
            for future in concurrent.futures.as_completed(future_to_event):
                url, home, away, league, start_time = future_to_event[future]
                try:
                    streams = future.result()
                except Exception as e:
                    print(f"[LiveTV] ❌ Error en evento {url}: {e}")
                    streams = []

                event = Event(
                    id=url,
                    name=f"{home} vs {away}",
                    url=url,
                    league=league or "",
                    home=home,
                    away=away,
                    match_time=start_time,
                    start_time=0,
                    provider=self.name,
                    streams=streams,
                    home_logo=get_team_logo(home),
                    away_logo=get_team_logo(away),
                    league_logo=get_team_logo(league)
                )
                events.append(event)

        return events

    def load_streams(self, event_url: str) -> List[Stream]:
        streams: List[Stream] = []

        try:
            resp = requests.get(event_url, headers=UA_HEADERS, timeout=20, verify=False)
            resp.raise_for_status()
        except Exception as e:
            print(f"[LiveTV] Error al cargar evento {event_url}: {e}")
            return streams

        soup = BeautifulSoup(resp.text, "html.parser")
        found = 0

        for table in soup.find_all("table", class_="lnktbj"):
            parent_td = table.find_parent("td")
            if not parent_td:
                continue

            play_link = table.find("a", href=True)
            if not play_link or "webplayer2.php" not in play_link["href"]:
                continue

            href = play_link["href"]
            stream_url = urljoin("https://cdn.livetv869.me/", href)

            span_name = table.find("span", id=lambda x: x and x.startswith("ltonq"))
            stream_name = span_name.get_text(strip=True) if span_name else f"Stream {found + 1}"

            streams.append(Stream(
                name=stream_name,
                url=stream_url,
                source=self.name,
                language=None
            ))
            found += 1
        
        # DEBUG
        #if found:
           # print(f"[LiveTV] {found} stream(s) encontrados para: {event_url}")
        #else:
        #    print(f"[LiveTV] No se encontraron streams en: {event_url}")

        return streams


# DEBUG
if __name__ == "__main__":
    liveTVProvider = LiveTVProvider()
    events = liveTVProvider.fetch_events()
    for e in events:
        print(f"{e.name} | Fecha: {e.start_time} | Liga: {e.league} | Streams: {len(e.streams)}")
        for s in e.streams:
            print(f" → {s.name}: {s.url}")
