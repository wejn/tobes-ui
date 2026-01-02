"""Common utility classes for various use-cases."""

from collections import deque
import time
from typing import Any, Literal

import numpy as np

from tobes_ui.spectrometer import Spectrum



class AttrDict(dict):  # pylint: disable=too-many-instance-attributes
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
        for k, v in other.items():  # pylint: disable=invalid-name
            if isinstance(v, dict) and not isinstance(v, AttrDict):
                v = AttrDict(v)  # pylint: disable=invalid-name
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
        self._running_sums = {}
        self._max_deques = {}
        self.func = func
        self.window_size = window_size

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
        self._rebuild_running_sums()
        self._max_deques.clear()

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
        if value == "avg":
            self._rebuild_running_sums()
        else:
            self._max_deques.clear()

    def clear(self):
        """Clear all buffers"""
        for _field_name, buffer in self._buffers.items():
            buffer.clear()
        self._running_sums.clear()
        self._max_deques.clear()

    def _rebuild_running_sums(self):
        """Rebuild running sums from current buffer state"""
        if self._op != "avg":
            return

        self._running_sums.clear()
        for field_name, buffer in self._buffers.items():
            if len(buffer) > 0:
                stacked = np.stack(list(buffer), axis=0)
                self._running_sums[field_name] = np.sum(stacked, axis=0)

    def add(self, instance: Spectrum) -> Spectrum:
        """Add value (instance of spectrum) and return aggregated"""
        for field_name, buffer in self._buffers.items():
            value = getattr(instance, field_name)
            if isinstance(value, dict):
                new_array = np.array(list(value.values()))
            else:
                new_array = np.array(value)

            if self._op == "avg":
                if field_name not in self._running_sums:
                    self._running_sums[field_name] = np.zeros_like(new_array, dtype=np.float64)

                if len(buffer) >= self._window_size:
                    old_array = buffer.popleft()
                    self._running_sums[field_name] -= old_array

                buffer.append(new_array)
                self._running_sums[field_name] += new_array

            else:  # max
                if field_name not in self._max_deques:
                    self._max_deques[field_name] = [deque() for _ in range(len(new_array))]
                    for arr in buffer:
                        max_deques = self._max_deques[field_name]
                        for i, val in enumerate(arr):
                            while max_deques[i] and max_deques[i][-1] < val:
                                max_deques[i].pop()
                            max_deques[i].append(val)

                if len(buffer) >= self._window_size:
                    oldest_array = buffer.popleft()
                    max_deques = self._max_deques[field_name]
                    for i, val in enumerate(oldest_array):
                        if max_deques[i] and max_deques[i][0] == val:
                            max_deques[i].popleft()

                buffer.append(new_array)

                max_deques = self._max_deques[field_name]
                for i, val in enumerate(new_array):
                    while max_deques[i] and max_deques[i][-1] < val:
                        max_deques[i].pop()
                    max_deques[i].append(val)

        return self._compute_aggregate(instance)

    def _agg_op(self, field_name):
        buffer = self._buffers[field_name]
        buf_len = len(buffer)

        if buf_len == 0:
            return None

        if self._op == "avg":
            return list(self._running_sums[field_name] / buf_len)

        # max
        if field_name not in self._max_deques:
            return None
        max_deques = self._max_deques[field_name]
        return [dq[0] if dq else float('-inf') for dq in max_deques]

    def _compute_aggregate(self, template: Any) -> Any:
        if not template.y_axis or template.y_axis == 'counts':
            template.y_axis = "Counts"

        if self.window_size > 1:
            spd_raw_agg = self._agg_op('spd_raw')
            spd_agg = self._agg_op('spd')

            if spd_raw_agg is not None:
                template.spd_raw = spd_raw_agg
            if spd_agg is not None:
                template.spd = dict(zip(template.spd.keys(), spd_agg))

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
