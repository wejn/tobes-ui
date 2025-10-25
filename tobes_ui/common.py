"""Common utility classes for various use-cases."""

from collections import deque


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
    """Sliding max of window_size; useful e.g. to avoid jumpy Y axis."""

    def __init__(self, window_size=5):
        self._window_size = window_size
        self._data = deque()
        self._decreasing = deque()  # Monotonic decreasing queue

    def add(self, value):
        """Add a new value and return current max."""
        self._data.append(value)

        # Remove smaller elements from the right
        while self._decreasing and self._decreasing[-1] < value:
            self._decreasing.pop()
        self._decreasing.append(value)

        # If window too large, evict oldest
        if len(self._data) > self._window_size:
            old = self._data.popleft()
            if old == self._decreasing[0]:
                self._decreasing.popleft()

        return self._decreasing[0]

    @property
    def window_size(self) -> int:
        return self._window_size

    @window_size.setter
    def window_size(self, new_size: int):
        """Reconfigure the window size dynamically."""
        if new_size < 1:
            raise ValueError("Window size must be >= 1")

        self._window_size = new_size

        # Trim stored _data if necessary
        while len(self._data) > self._window_size:
            old = self._data.popleft()
            if self._decreasing and old == self._decreasing[0]:
                self._decreasing.popleft()

    @property
    def current_max(self):
        """Return current max without adding a new value."""
        if not self._decreasing:
            return None
        return self._decreasing[0]
