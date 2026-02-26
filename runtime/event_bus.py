"""
Event Bus
=========
Lightweight in-process event system for decoupling the research 
pipeline from external consumers (like SSE streams or websockets).
"""
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger("aro.event_bus")

class EventBus:
    """Simple pub/sub event bus."""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}

    def on(self, event_type: str, callback: Callable) -> None:
        """Register a callback for an event type."""
        self._listeners.setdefault(event_type, []).append(callback)

    def emit(self, event_type: str, data: Any = None) -> None:
        """Emit an event to all registered listeners."""
        for cb in self._listeners.get(event_type, []):
            try:
                cb(data)
            except Exception as e:
                logger.error("EventBus listener error for %s: %s", event_type, e)
                # Never crash the pipeline due to a listener failure
                pass

    def clear(self) -> None:
        """Remove all registered listeners."""
        self._listeners.clear()
