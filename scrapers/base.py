from abc import ABC, abstractmethod
from typing import List
from .models import Event

class BaseProvider(ABC):
    name: str

    @abstractmethod
    def fetch_events(self) -> List[Event]:
        pass
