import requests
from typing import List
from ..models import Event, Stream
from ..base import BaseProvider
from .utils.logos import get_team_logo

class KakarotfootProvider(BaseProvider):
    name = "Kakarotfoot"
    FEED = "https://kakarotfoot.ru/json.php"

    def fetch_events(self) -> List[Event]:
        events = []
        try:
            data = requests.get(self.FEED, timeout=10).json()
        except:
            return events

        for obj in data:
            es_channels = obj.get("streams", [])

            home = obj.get("home", "")
            away = obj.get("away", "")
            league = obj.get("league", "")

            event = Event(
                id=obj["id"],
                name=f"{home} vs {away}",
                url=f"https://kakarotfoot.ru/{obj['url']}",
                league=league,
                home=home,
                away=away,
                start_time=int(obj.get("time", 0)),
                provider="Kakarotfoot",
                streams=[],
                home_logo=get_team_logo(home),
                away_logo=get_team_logo(away),
                league_logo=get_team_logo(league)
            )

            for s in es_channels:
                ch = s.get("ch")
                if not ch:
                    continue
                display = s.get("name") or f"Canal {ch}"
                lang = s.get("lang")

                event.streams.append(Stream(
                    name=display,
                    url=f"https://kakarotfoot.ru/yu/3/{ch}",
                    language=lang,
                    source="Kakarotfoot"
                ))

            events.append(event)

        return events
