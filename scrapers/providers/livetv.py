from __future__ import annotations
from typing import List, Tuple
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
import concurrent.futures
from datetime import datetime

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

            if not td_parent.find("img", src="//cdn.livetv869.me/img/live.gif"):
                continue  # solo eventos en vivo

            event_url = urljoin("https://livetv.sx", a_tag["href"])
            event_text = a_tag.get_text(strip=True)

            home = away = league = date_text = ""

            for sep in [" – ", " - ", " vs ", " Vs ", " v ", "–", "-"]:
                if sep in event_text:
                    home, away = map(str.strip, event_text.split(sep, 1))
                    break
            else:
                home, away = "", ""

            span = td_parent.find("span", class_="evdesc")
            if span:
                full_text = span.get_text(separator="|", strip=True)
                parts = full_text.split("|")
                date_text = parts[0].strip() if len(parts) > 0 else ""
                league = parts[1].strip(" ()") if len(parts) > 1 else ""

            event_data.append((event_url, home, away, league, date_text))

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_event = {
                executor.submit(self._build_event_with_streams, *data): data[0]
                for data in event_data
            }
            for future in concurrent.futures.as_completed(future_to_event):
                try:
                    event = future.result()
                    if event:
                        events.append(event)
                except Exception as e:
                    print(f"[LiveTV] ❌ Error en evento {future_to_event[future]}: {e}")

        return events

    def _build_event_with_streams(self, url: str, home: str, away: str, league: str, start: str) -> Event | None:
        try:
            resp = requests.get(url, headers=UA_HEADERS, timeout=20, verify=False)
            resp.raise_for_status()
        except Exception as e:
            print(f"[LiveTV] Error al cargar evento {url}: {e}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        if not home or not away:
            h1 = soup.select_one("h1.sporttitle b")
            if h1:
                text = h1.get_text(strip=True)
                for sep in [" – ", " - ", " vs ", " Vs ", " v ", "–", "-"]:
                    if sep in text:
                        home, away = map(str.strip, text.split(sep, 1))
                        break

        if not league:
            liga_tag = soup.select_one("td.small b a.menu")
            if liga_tag:
                league = liga_tag.get_text(strip=True)

        match_time = start
        try:
            time_tag = soup.select_one("td.small b")
            if time_tag:
                match_text = time_tag.get_text(strip=True)
                match = re.search(r"\d{1,2} \w+ \d{4} at \d{1,2}:\d{2}", match_text)
                if match:
                    match_time = datetime.strptime(match.group(), "%d %B %Y at %H:%M")
        except Exception as e:
            print(f"[LiveTV] Error procesando match_time para {url}: {e}")

        streams: List[Stream] = []
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

            response = requests.get(stream_url, headers=UA_HEADERS, timeout=20, verify=False)
            response.raise_for_status()
            
            # Buscar iframe en voodc
            soup_stream = BeautifulSoup(response.text, "html.parser")
            # Buscar todos los iframes y filtrar solo los válidos
            # Buscar iframe directo con height=480 (YouTube o algunos simples)
            iframes = soup_stream.find_all("iframe")
            iframe_src = None

            for fr in iframes:
                src = fr.get("src")
                if not src:
                    continue
                src = urljoin(stream_url, src)

                # Aceptamos cualquier iframe real de reproductor
                if fr.get("height") == "480" or fr.get("allowfullscreen") == "true":
                    iframe_src = src
                    break

            #  Si no existe iframe visible, hay que revisar scripts JS
            if not iframe_src:
                for script in soup_stream.find_all("script"):
                    if not script.string:
                        continue

                    content = script.string

                    # Buscar URLs que cargan el iframe final
                    m = re.search(r'(https?://[^"\']+embed[^"\']+)', content)
                    if m:
                        iframe_src = m.group(1)
                        break

                    # Buscar llamadas tipo load("/embed/XYZ")
                    m = re.search(r'load\(["\']([^"\']+)["\']', content)
                    if m:
                        iframe_src = urljoin(stream_url, m.group(1))
                        break

            # Última oportunidad: buscar en atributos data-*
            if not iframe_src:
                for attr in ["data-src", "data-url", "data-iframe"]:
                    for tag in soup_stream.find_all(attrs={attr: True}):
                        iframe_src = urljoin(stream_url, tag[attr])
                        break
                    if iframe_src:
                        break

            # Si aún no hay nada, no hay stream válido
            if not iframe_src:
                # print(f"[LiveTV] No se encontró iframe final para {stream_url}")
                continue
            else:
                print(iframe_src)

            streams.append(Stream(
                name=stream_name,
                url=iframe_src,
                source=self.name
            ))

            found += 1

        return Event(
            id=url,
            name=f"{home} vs {away}",
            url=url,
            league=league or "Próximamente",
            home=home or "Próximamente",
            away=away or "Próximamente",
            match_time=match_time,
            start_time=0,
            provider=self.name,
            streams=streams,
            home_logo=get_team_logo(home),
            away_logo=get_team_logo(away),
            league_logo=get_team_logo(league)
        )


# DEBUG
if __name__ == "__main__":
    liveTVProvider = LiveTVProvider()
    events = liveTVProvider.fetch_events()
    
    print(f"\n🟢 Total de eventos en vivo: {len(events)}\n")

"""
    for e in events:
        print("=" * 80)
        print(f"📺 Nombre del evento : {e.name}")
        print(f"🏆 Liga              : {e.league}")
        print(f"⏰ Fecha/Hora        : {e.match_time}")
        print(f"🏠 Local             : {e.home}")
        print(f"🚌 Visitante         : {e.away}")
        print(f"🖼 Logo Local        : {e.home_logo or 'N/A'}")
        print(f"🖼 Logo Visitante    : {e.away_logo or 'N/A'}")
        print(f"🖼 Logo Liga         : {e.league_logo or 'N/A'}")
        print(f"🔗 URL del evento    : {e.url}")
        print(f"🎥 Streams ({len(e.streams)}):")
        for s in e.streams:
            print(f"   • {s.name or 'Sin nombre'} => {s.url}")
        print("=" * 80 + "\n")
#"""