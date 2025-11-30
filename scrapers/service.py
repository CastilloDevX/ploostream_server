from typing import List
from .models import Event
from .base import BaseProvider

class ScraperService:
    def __init__(self, providers: List[BaseProvider]):
        self.providers = providers

    def build_events(self) -> List[Event]:
        events = []

        for p in self.providers:
            try:
                events.extend(p.fetch_events())
            except Exception:
                continue

        # eliminar duplicados por id+liga
        seen = set()
        unique = []
        for e in sorted(events, key=lambda x: x.start_time):
            key = (e.id, e.league)
            if key in seen:
                continue
            seen.add(key)
            unique.append(e)

        return unique
