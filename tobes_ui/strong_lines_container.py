"""Container for StrongLines to allow efficient searches"""

import bisect
from itertools import chain
from typing import Dict, List

from tobes_ui.strong_lines import StrongLine

class StrongLinesContainer:
    """Holds strong lines and provides effective interface for search and plotting"""

    def __init__(self, strong_lines: Dict[str, List[StrongLine]]):
        self._all_lines = list(chain.from_iterable(strong_lines.values()))
        self._all_lines.sort(key=lambda x: x.wavelength)
        self._keys = [obj.wavelength for obj in self._all_lines]
        self._values = [obj.intensity for obj in self._all_lines]

    def find_in_range(self, min_val, max_val):
        """Find all strong lines within min/max range"""
        min_idx = bisect.bisect_left(self._keys, min_val)
        max_idx = bisect.bisect_right(self._keys, max_val)
        return self._all_lines[min_idx:max_idx]

    def plot_data(self):
        """Return data for plotting"""
        return (self._keys, self._values)

    def __len__(self):
        return len(self._all_lines)

    def __repr__(self):
        if len(self):
            wl_min, wl_max = self._keys[0], self._keys[-1]
            return (f"<{__name__}.StrongLinesContainer(n_lines={len(self)}, "
                    f"wavelength_range=({wl_min:.2f}, {wl_max:.2f}))>")
        return f"<{__name__}.StrongLinesContainer(empty)>"
