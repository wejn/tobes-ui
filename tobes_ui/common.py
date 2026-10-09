"""Common utility classes for various use-cases."""

from collections import deque
import copy
import time
from typing import Literal

import numpy as np
from scipy.ndimage import convolve1d

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


class Aggregator:
    """Aggregates readings over a sliding window."""

    _VALID_FUNCS = {"avg", "max", "mdn"}

    def __init__(
        self,
        window_size: int,
        func: Literal["avg", "max", "mdn"] = "avg",
    ):
        if window_size < 1:
            raise ValueError("window_size must be positive")
        if func not in self._VALID_FUNCS:
            raise ValueError(
                f"Invalid func {func!r}; "
                f"expected one of {sorted(self._VALID_FUNCS)}"
            )

        self._window_size = window_size
        self._func = func

        # Lazily initialized from the first instance.
        self._data = None
        self._sum = None
        self._max = None

        self._size = 0
        self._pos = 0

    @property
    def window_size(self) -> int:
        """Get current window size."""
        return self._window_size

    @window_size.setter
    def window_size(self, value: int):
        """Resize the window, retaining the newest values."""
        if value < 1:
            raise ValueError("window_size must be positive")

        if value == self._window_size:
            return

        # No data yet: just change the configured capacity.
        if self._data is None:
            self._window_size = value
            return

        # Get existing samples in oldest -> newest order.
        current = self._ordered_data()

        # Keep only the newest `value` samples if shrinking.
        if len(current) > value:
            current = current[-value:]

        self._window_size = value

        self._rebuild(current)


    @property
    def func(self) -> str:
        """Get current func."""
        return self._func

    @func.setter
    def func(self, value: Literal["avg", "max", "mdn"]):
        """Set aggregating func to use."""
        if value not in self._VALID_FUNCS:
            raise ValueError(
                f"Invalid func {value!r}; "
                f"expected one of {sorted(self._VALID_FUNCS)}"
            )

        self._func = value

    def clear(self):
        """Clear all buffers while retaining configuration."""
        self._size = 0
        self._pos = 0

        if self._sum is not None:
            self._sum.fill(0)

        if self._max is not None:
            self._max.fill(-np.inf)

    def add(self, instance):
        """Add a reading and return the processed result."""
        instance = np.asarray(instance)

        if instance.ndim != 1:
            raise ValueError(
                f"instance must be 1-dimensional, got shape {instance.shape}"
            )

        # First value establishes the number of features.
        if self._data is None:
            self._initialize(instance)

        elif instance.shape[0] != self._data.shape[1]:
            raise ValueError(
                f"Expected {self._data.shape[1]} features, "
                f"got {instance.shape[0]}"
            )

        # Convert to our storage dtype.
        instance = instance.astype(self._data.dtype, copy=False)

        if self._size < self._window_size:
            # Buffer isn't full yet.
            self._data[self._pos] = instance

            self._sum += instance
            self._max = np.maximum(self._max, instance)

            self._size += 1
            self._pos = (self._pos + 1) % self._window_size

        else:
            # Replace oldest instance.
            old = self._data[self._pos]

            self._sum += instance - old
            self._data[self._pos] = instance

            # If the removed value was the max, recompute only
            # the affected columns.
            was_max = old >= self._max

            self._max = np.maximum(self._max, instance)

            if np.any(was_max):
                self._max[was_max] = np.max(
                    self._data[:self._size, was_max],
                    axis=0,
                )

            self._pos = (self._pos + 1) % self._window_size

        return self._aggregate()

    def _initialize(self, instance):
        n_features = instance.shape[0]

        # Preserve input precision for the stored spectra.
        dtype = instance.dtype
        if not np.issubdtype(dtype, np.floating):
            dtype = np.float32

        self._data = np.empty(
            (self._window_size, n_features),
            dtype=dtype,
        )

        # Accumulate averages in float64.
        self._sum = np.zeros(
            n_features,
            dtype=np.float64,
        )

        self._max = np.full(
            n_features,
            -np.inf,
            dtype=dtype,
        )

    def _aggregate(self):
        if self._size == 0:
            return None

        if self._func == "avg":
            return self._sum / self._size

        if self._func == "max":
            return self._max.copy()

        # Median.
        return np.median(
            self._data[:self._size],
            axis=0,
        )

    def _ordered_data(self):
        """Return current data in oldest -> newest order."""
        if self._size == 0:
            return self._data[:0]

        if self._size < self._window_size:
            return self._data[:self._size].copy()

        # Ring has wrapped.
        return np.concatenate(
            (
                self._data[self._pos:],
                self._data[:self._pos],
            )
        )

    def _rebuild(self, data):
        """Reallocate storage and rebuild incremental aggregates."""
        n_features = self._data.shape[1]

        self._data = np.empty(
            (self._window_size, n_features),
            dtype=self._data.dtype,
        )

        self._sum = np.zeros(
            n_features,
            dtype=np.float64,
        )

        self._max = np.full(
            n_features,
            -np.inf,
            dtype=self._data.dtype,
        )

        self._size = len(data)

        # Store existing data in oldest -> newest order.
        if self._size:
            self._data[:self._size] = data

            self._sum[:] = self._data[:self._size].sum(
                axis=0,
                dtype=np.float64,
            )

            self._max[:] = self._data[:self._size].max(axis=0)

        # Next insertion goes after the newest element.
        self._pos = self._size % self._window_size

    def describe(self):
        """Describe currently active aggregation function"""
        if self._size == self._window_size:
            return f"(agg:{self._func}, win:{self._size})"
        return f"(agg:{self._func}, win:{self._size}/{self._window_size})"

    def last(self):
        """Return last value for current aggregator (what add() would)"""
        return self._aggregate()


class SpectrumProcessor:
    """Processes spectrum readings over given window_size with given func"""

    _VALID_FUNCS = {}
    _PROCESSOR = None  # Provide!
    _MIN_ACTIVE_WINDOW = 1  # min window with which the processing is active

    def __init__(self, window_size: int, func: str):
        if func not in self._VALID_FUNCS:
            raise ValueError(f"Invalid func: {func!r}")
        if not callable(self._PROCESSOR):
            raise ValueError("no processor provided")
        self._buffers = {
                'spd': self._PROCESSOR(window_size, func),
                'spd_raw': self._PROCESSOR(window_size, func),
        }
        self._func = func
        self._window_size = window_size
        self._items = 0
        self._last = None

    @property
    def window_size(self) -> int:
        """Get current window size"""
        return self._window_size

    @window_size.setter
    def window_size(self, value: int):
        """Resize the window"""
        for _field_name, buffer in self._buffers.items():
            buffer.window_size = value
        self._window_size = value
        self._items = self._window_size if self._window_size < self._items else self._items

    @property
    def func(self) -> str:
        """Get current func"""
        return self._func

    @func.setter
    def func(self, func: str):
        """Set processing func to use"""
        if func not in self._VALID_FUNCS:
            raise ValueError(f"Invalid func: {func!r}")
        for _field_name, buffer in self._buffers.items():
            buffer.func = func
        self._func = func

    def clear(self):
        """Clear all buffers"""
        for _field_name, buffer in self._buffers.items():
            buffer.clear()
        self._items = 0
        self._last = None

    def add(self, instance: Spectrum) -> Spectrum:
        """Add value (instance of spectrum) and return processed"""
        update = {}
        for field_name, buffer in self._buffers.items():
            value = getattr(instance, field_name)
            if isinstance(value, dict):
                new_array = np.array(list(value.values()))
            else:
                new_array = np.array(value)
            update[field_name] = buffer.add(new_array)
        if self._items < self._window_size:
            self._items += 1

        self._last = instance

        return self._apply(update)

    def _apply(self, update):
        if not self._last:
            return None

        instance = copy.copy(self._last)

        if self.window_size >= self._MIN_ACTIVE_WINDOW:
            if not instance.y_axis or instance.y_axis == 'counts':
                instance.y_axis = "Counts"

            instance.spd_raw = update['spd_raw']
            instance.spd = dict(zip(instance.spd.keys(), update['spd']))
            instance.y_axis = f"{instance.y_axis} {self._buffers['spd'].describe()}"
            # FIXME: mark transformation in metadata

        return instance

    def last(self):
        """Return last spectrum with current function (what add() would)"""
        update = {}
        for field_name, buffer in self._buffers.items():
            update[field_name] = buffer.last()

        return self._apply(update)

    def __repr__(self):
        return (f"<{__name__}.{__class__}(op={self.func},"
                f" window_size={self.window_size}, buf={self._items})>")


class SpectrumAggregator(SpectrumProcessor):
    """Aggregates spectrum readings over given window_size with given func"""

    _VALID_FUNCS = {"avg", "max", "mdn"}
    _PROCESSOR = Aggregator
    _MIN_ACTIVE_WINDOW = 2

    def __init__(self, window_size: int, func: Literal["avg", "max", "mdn"] = "avg"):
        super().__init__(window_size, func)


class Smoother:
    """Smooths readings over a given window."""

    _VALID_FUNCS = {"boxcar", "triangular", "gaussian"}

    def __init__(
        self,
        window_size: int,
        func: Literal["boxcar", "triangular", "gaussian"] = "boxcar",
    ):
        if window_size < 0:
            raise ValueError("window_size must be positive or zero")
        if func not in self._VALID_FUNCS:
            raise ValueError(
                f"Invalid func {func!r}; "
                f"expected one of {sorted(self._VALID_FUNCS)}"
            )

        self._window_size = window_size
        self._func = func

        self._data = None

    @property
    def window_size(self) -> int:
        """Get current window size."""
        return self._window_size

    @window_size.setter
    def window_size(self, value: int):
        """Resize the window, retaining the newest values."""
        if value < 0:
            raise ValueError("window_size must be positive or zero")
        self._window_size = value

    @property
    def func(self) -> str:
        """Get current func."""
        return self._func

    @func.setter
    def func(self, value: Literal["boxcar", "triangular", "gaussian"]):
        """Set aggregating func to use."""
        if value not in self._VALID_FUNCS:
            raise ValueError(
                f"Invalid func {value!r}; "
                f"expected one of {sorted(self._VALID_FUNCS)}"
            )

        self._func = value

    def clear(self):
        """Clear all buffers while retaining configuration."""
        self._data = None

    def add(self, instance):
        """Add a reading and return the smoothed result."""
        self._data = instance

        return self.last()

    def last(self):
        """Return last value for current aggregator (what add() would)"""
        if self._data is None:
            return None
        y = np.asarray(self._data)
        x = np.arange(-self._window_size, self._window_size + 1)

        match self._func:
            case "boxcar":
                kernel = np.ones(2 * self._window_size + 1)

            case "triangular":
                kernel = self._window_size + 1 - np.abs(x)

            case "gaussian":
                sigma = max(self._window_size / 2, 0.5)
                kernel = np.exp(-0.5 * (x / sigma) ** 2)

            case _:
                raise ValueError("internal error: Unknown method")

        kernel = kernel / kernel.sum()

        return convolve1d(y, kernel, mode="nearest")

    def describe(self):
        """Describe currently active smoothing function"""
        return f"(sm:{self._func}, win:{self._window_size})"


class SpectrumSmoother(SpectrumProcessor):
    """Smooths spectrum readings over given width (window) with given func"""

    _VALID_FUNCS = {"boxcar", "triangular", "gaussian"}
    _PROCESSOR = Smoother
    _MIN_ACTIVE_WINDOW = 1  # window of 1 means one pixel on each side


class SpectrumAggregatorSmoother:
    """Chain of aggregator and smoother."""

    def __init__(self, agg : SpectrumAggregator, sm: SpectrumSmoother):
        self._agg = agg
        self._sm = sm

    def add(self, instance):
        """Add value (instance of spectrum) and return processed"""
        return self._sm.add(self._agg.add(instance))

    def last(self):
        """Return last spectrum with current function (what add() would)"""
        a = self._agg.last()
        if a:
            return self._sm.add(a)
        return None

    def clear(self):
        """Clear all buffers while retaining configuration."""
        self._agg.clear()
        self._sm.clear()
