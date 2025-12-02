from dataclasses import dataclass, field, asdict
from typing import List, Optional

@dataclass
class Stream:
    name: str
    url: str
    language: Optional[str] = None
    source: Optional[str] = None

    def to_dict(self):
        return asdict(self)

@dataclass
class Event:
    id: str
    name: str
    url: str
    league: str
    home: str
    away: str
    start_time: int
    provider: str
    streams: List[Stream]

    home_logo: str = ""
    away_logo: str = ""
    league_logo: str = ""

    match_time: str = ""

    def to_dict(self):
        return asdict(self)
