"""Common utility classes for various use-cases."""

from collections import deque
import time
from typing import Any, Literal

import numpy as np

from tobes_ui.spectrometer import Spectrum



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


class SpectrumAggregator:
    """Aggregates spectrum readings over given window_size with given func"""

    def __init__(self, window_size: int, func: Literal["avg", "max"] = "avg"):
        self._buffers = {
            'spd': deque(),
            'spd_raw': deque(),
        }
        self.func = func  # invariants by setter
        self.window_size = window_size  # invariants by setter

    @property
    def window_size(self) -> int:
        """Get current window size"""
        return self._window_size

    @window_size.setter
    def window_size(self, value: int):
        """Resize the window"""
        if value <= 0:
            raise ValueError("window_size must be positive")
        self._window_size = value
        for buffer in self._buffers.values():
            while len(buffer) > value:
                buffer.popleft()

    @property
    def func(self) -> str:
        """Get current func"""
        return self._op

    @func.setter
    def func(self, value: Literal["avg", "max"]):
        """Set aggregating func to use (avg or max)"""
        if value not in ("avg", "max"):
            raise ValueError("func must be 'avg' or 'max'")
        self._op = value

    def clear(self):
        """Clear all buffers"""
        for _field_name, buffer in self._buffers.items():
            buffer.clear()

    def add(self, instance: Spectrum) -> Spectrum:
        """Add value (instance of spectrum) and return aggregated"""
        for field_name, buffer in self._buffers.items():
            value = getattr(instance, field_name)
            if isinstance(value, dict):
                buffer.append(list(value.values()))
            else:
                buffer.append(value.copy())
            while len(buffer) > self._window_size:
                buffer.popleft()

        return self._compute_aggregate(instance)


    def _agg_op(self, data):
        stacked = np.stack(data, axis=0)

        if self._op == "avg":
            return list(np.mean(stacked, axis=0))
        # max
        return list(np.max(stacked, axis=0))

    def _compute_aggregate(self, template: Any) -> Any:
        if not template.y_axis or template.y_axis == 'counts':
            template.y_axis = "Counts"

        if self.window_size > 1:
            template.spd_raw = self._agg_op(self._buffers['spd_raw'])
            template.spd = dict(zip(template.spd.keys(), self._agg_op(self._buffers['spd'])))

            buf_len = len(self._buffers['spd'])
            if buf_len < self.window_size:
                template.y_axis += f" (func: {self.func}, win: {buf_len}/{self.window_size})"
            else:
                template.y_axis += f" (func: {self.func}, win: {self.window_size})"

        return template

    def __repr__(self):
        buf_len = len(self._buffers['spd'])
        return (f"<{__name__}.SpectrumAggregator(op={self.func},"
                f" window_size={self.window_size}, buf={buf_len})>")
