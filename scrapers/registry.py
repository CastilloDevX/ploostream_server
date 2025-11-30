from typing import List
from .base import BaseProvider

from .providers.kakarotfoot import KakarotfootProvider
from .providers.tiroalpalo import TiroalpaloProvider
from .providers.kevinsport import KevinsportProvider
from .providers.livetv import LiveTVProvider

provider_registry: List[BaseProvider] = [
    KakarotfootProvider(),
    TiroalpaloProvider(),
    KevinsportProvider(),
    LiveTVProvider(),
]