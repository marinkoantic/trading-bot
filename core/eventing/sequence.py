from threading import Lock


class EventSequence:
    _sequence: int = 0
    _lock = Lock()

    @classmethod
    def next(cls) -> int:
        with cls._lock:
            cls._sequence += 1
            return cls._sequence