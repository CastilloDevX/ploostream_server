from __future__ import annotations
from typing import List
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
import concurrent.futures
from datetime import datetime
from playwright.sync_api import sync_playwright

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

    # ============================================================
    # FETCH EVENTS
    # ============================================================
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
                continue

            event_url = urljoin("https://livetv.sx", a_tag["href"])
            event_text = a_tag.get_text(strip=True)

            home = away = league = date_text = ""

            for sep in [" – ", " - ", " vs ", " Vs ", " v ", "–", "-"]:
                if sep in event_text:
                    home, away = map(str.strip, event_text.split(sep, 1))
                    break

            span = td_parent.find("span", class_="evdesc")
            if span:
                parts = span.get_text("|").split("|")
                if len(parts) > 1:
                    league = parts[1].strip(" ()")

            event_data.append((event_url, home, away, league))

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


    # ============================================================
    # SCRAP STREAMS WITH FALLBACK
    # ============================================================
    def _build_event_with_streams(self, url: str, home: str, away: str, league: str) -> Event | None:

        # Load event page
        try:
            resp = requests.get(url, headers=UA_HEADERS, timeout=20, verify=False)
            resp.raise_for_status()
        except:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        streams = []
        found = 0

        for table in soup.find_all("table", class_="lnktbj"):

            play_link = table.find("a", href=True)
            if not play_link or "webplayer2.php" not in play_link["href"]:
                continue

            stream_url = urljoin("https://cdn.livetv869.me/", play_link["href"])

            # Try normal request
            try:
                r2 = requests.get(stream_url, headers=UA_HEADERS, timeout=20, verify=False)
                r2.raise_for_status()
            except:
                continue

            soup2 = BeautifulSoup(r2.text, "html.parser")

            iframe_src = None

            # ============================================================
            # 1) First: original YOUTUBE logic (height=480 or allowfullscreen)
            # ============================================================
            for fr in soup2.find_all("iframe"):
                src = fr.get("src")
                if not src:
                    continue
                    
                full = urljoin(stream_url, src)

                h = fr.get("height")
                allow = fr.get("allowfullscreen")

                # print("→ Candidate iframe:", full)

                # YOUTUBE by old logic
                if h == "480" or allow == "true":
                    iframe_src = full
                    # print("   ✔ Valid YOUTUBE (height=480 / allowfullscreen)")
                    break

                # Modern youtube detection
                if "youtube.com/embed" in full.lower():
                    iframe_src = full
                    # print("   ✔ Valid YOUTUBE (embed)")
                    break

                # EMB logic
                if "emb" in full.lower():
                    iframe_src = full
                    # print("   ✔ Valid EMB")
                    break

            # ============================================================
            # 2) Script-based URL (old logic)
            # ============================================================
            if not iframe_src:
                for script in soup2.find_all("script"):
                    content = script.string or ""
                    m = re.search(r'(https?://[^"\']+embed[^"\']+)', content)
                    if m:
                        iframe_src = m.group(1)
                        # print("   ✔ Found embed in script")
                        break


            # ============================================================
            # 3) If still nothing, use Playwright
            # ============================================================
            if not iframe_src:
                # print(f"⚠ Playwright scanning: {stream_url}")

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()

                    try:
                        page.goto(stream_url, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(1100)

                        iframes = page.query_selector_all("iframe")
                        # print("🔍 Playwright found:", len(iframes), "iframes")

                        for fr in iframes:
                            src = fr.get_attribute("src")
                            if not src:
                                continue

                            full = urljoin(stream_url, src)
                            # print("→ PW Candidate:", full)

                            # EMB
                            if "emb" in full.lower():
                                iframe_src = full
                                # print("   ✔ EMB (PW)")
                                break

                            # Youtube embed
                            if "youtube.com/embed" in full.lower():
                                iframe_src = full
                                # print("   ✔ YouTube (PW)")
                                break

                        if not iframe_src:
                            # Last fallback: script embed
                            m = re.search(r'(https?://[^"\']+embed[^"\']+)', page.content())
                            if m:
                                iframe_src = m.group(1)
                                # print("   ✔ Script embed fallback (PW)")

                    except Exception as e:
                        print("[PW ERROR]", e)

                    browser.close()


            # ============================================================
            # If still nothing: ignore stream
            # ============================================================
            if not iframe_src:
                # print("❌ No valid iframe found\n")
                continue

            # Add valid stream
            streams.append(Stream(
                name=f"Stream {found+1}",
                url=iframe_src,
                source=self.name
            ))
            found += 1

        # Return Event
        return Event(
            id=url,
            name=f"{home} vs {away}",
            url=url,
            league=league,
            home=home,
            away=away,
            match_time="",
            start_time=0,
            provider=self.name,
            streams=streams,
            home_logo=get_team_logo(home),
            away_logo=get_team_logo(away),
            league_logo=get_team_logo(league)
        )


# DEBUG
if __name__ == "__main__":
    scraper = LiveTVProvider()
    events = scraper.fetch_events()

    print("\n🟢 Total eventos:", len(events))
    for e in events:
        print("============")
        print(e.name)
        for s in e.streams:
            print(" →", s.url)
