"""Common utility classes for various use-cases."""

from collections import deque
import time


class AttrDict(dict):
    """Simple attribute dict, to turn a['name'] into a.name."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.update(*args, **kwargs)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as ex:
            raise AttributeError(f"'AttrDict' object has no attribute '{name}'") from ex

    def __setattr__(self, name, value):
        self[name] = value

    def update(self, *args, **kwargs):
        """Ensure all nested dicts are converted to AttrDicts recursively."""
        other = dict(*args, **kwargs)
        for k, v in other.items():
            if isinstance(v, dict) and not isinstance(v, AttrDict):
                v = AttrDict(v)
            super().__setitem__(k, v)


class SlidingMax:
    """Sliding max over a window_size seconds; useful e.g. to avoid jumpy Y axis."""

    def __init__(self, window_size=5.0):
        self._max_deque = deque()  # (timestamp, value); timestamps increasing, values decreasing
        self.window_size = window_size  # setter to enforce positivity

    @property
    def window_size(self) -> float:
        """Get current window size"""
        return self._window_size

    @window_size.setter
    def window_size(self, new_size: float) -> float:
        """Resize the window"""
        if new_size <= 0:
            raise ValueError(f'window_size expected positive, got {new_size}')
        self._window_size = new_size
        self._remove_expired_entries(time.time())

    def add(self, value):
        """Add new value, return max."""
        timestamp = time.time()

        self._remove_expired_entries(timestamp)

        # Remove elements from back that are smaller than current value
        # This is fine, as a value will be added, and that has > ts (assuming monotonic time)
        while self._max_deque and self._max_deque[-1][1] <= value:
            self._max_deque.pop()

        self._max_deque.append((timestamp, value))

        return self._max_deque[0][1] if self._max_deque else None

    def _remove_expired_entries(self, current_time: float):
        """Removes expired entries from the dbl-ended queue"""
        cutoff = current_time - self._window_size

        # Note:
        # Monotonic time is assumed; might lead to subtle "bugs" in rare cases;
        # so don't use this to run a nuclear power plant, ok? ;)
        while self._max_deque and self._max_deque[0][0] <= cutoff:
            self._max_deque.popleft()
