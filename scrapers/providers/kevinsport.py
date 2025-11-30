from __future__ import annotations
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import List

from ..base import BaseProvider
from ..models import Event, Stream
from .utils.logos import get_team_logo

class KevinsportProvider(BaseProvider):
    name = "KevinSport"
    URL = "https://kevinsport.pro/live/football/"

    def fetch_events(self) -> List[Event]:
        try:
            return asyncio.run(self.fetch_events_async())
        except Exception as e:
            print(f"[KevinSport] Error en fetch_events: {e}")
            return []

    async def fetch_events_async(self) -> List[Event]:
        events: List[Event] = []

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout
        ) as session:
            try:
                async with session.get(self.URL) as resp:
                    html = await resp.text()
            except Exception as e:
                print(f"[KevinSport] Error descargando página principal: {e}")
                return events

            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("table.table-hover tr")
            current_league = "(Desconocido)"
            tasks = []

            for row in rows:
                classes = row.get("class", [])

                # FILA DE LIGA
                if "table-info" in classes:
                    txt = row.get_text(strip=True)
                    if txt:
                        current_league = txt
                    continue

                # FILA DE PARTIDO
                if "table-dark" not in classes:
                    continue

                # Hora
                time_td = row.find("td", class_="matchtime")
                match_time = time_td.get_text(strip=True) if time_td else ""

                # Equipos
                title_td = row.find("td", class_="pnltblttl")
                title = title_td.get_text(strip=True) if title_td else "Unknown"

                if " Vs " in title:
                    home, away = title.split(" Vs ", 1)
                else:
                    home, away = title, ""

                name_final = (
                    f"{home} vs {away} ({match_time})"
                    if match_time else f"{home} vs {away}"
                )

                # Link de Watch
                watch = row.find("a", href=True)
                if not watch:
                    continue
                    
                event_page = watch["href"]
                if not event_page.startswith("http"):
                    event_page = f"https://kevinsport.pro{event_page}"

                event = Event(
                    id=event_page,
                    name=name_final,
                    url=event_page,
                    league=current_league,
                    home=home,
                    away=away,
                    start_time=0,
                    provider="KevinSport",
                    match_time=match_time,
                    streams=[],
                    home_logo=get_team_logo(home),
                    away_logo=get_team_logo(away),
                    league_logo=get_team_logo(current_league)
                )

                events.append(event)
                tasks.append(self._load_streams_async(session, event))

            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                print(f"[KevinSport] Error en gather de streams: {e}")
                
            return events

    async def _load_streams_async(self, session, event: Event):
        try:
            async with session.get(event.url) as r:
                html = await r.text()
        except Exception as e:
            print(f"[KevinSport] Error cargando evento {event.url}: {e}")
            return

        soup = BeautifulSoup(html, "html.parser")

        # Iframe principal
        iframe = soup.find("iframe")
        if iframe:
            src = iframe.get("src")
            if src:
                if not src.startswith("http"):
                    src = f"https:{src}" if src.startswith("//") else f"https://kevinsport.pro{src}"
                    
                event.streams.append(Stream(
                    name="Stream 1",
                    url=src,
                    source="KevinSport"
                ))

        # Streams secundarios
        stream_buttons = soup.find_all("a", string=lambda t: t and "Stream" in t)

        for btn in stream_buttons:
            href = btn.get("href")
            if not href:
                continue
                
            if not href.startswith("http"):
                href = f"https://kevinsport.pro{href}"

            try:
                async with session.get(href) as r2:
                    sub_html = await r2.text()
            except Exception as e:
                print(f"[KevinSport] Error en stream secundario {href}: {e}")
                continue

            sub_soup = BeautifulSoup(sub_html, "html.parser")
            sub_iframe = sub_soup.find("iframe")

            if not sub_iframe:
                continue

            src = sub_iframe.get("src")
            if src:
                if not src.startswith("http"):
                    src = f"https:{src}" if src.startswith("//") else f"https://kevinsport.pro{src}"
                    
                event.streams.append(Stream(
                    name=btn.get_text(strip=True),
                    url=src,
                    source="KevinSport"
                ))
