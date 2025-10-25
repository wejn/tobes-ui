"""Container for StrongLines to allow efficient searches"""

import bisect
from itertools import chain
from typing import Dict, List, Optional, Tuple

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

    def plot_data(
        self,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None
    ) -> Tuple[List[float], List[float]]:
        """Return data for plotting, optionally filtered by wavelength range"""
        if min_val is None and max_val is None:
            return self._keys, self._values

        # Determine index range using bisect
        min_idx = bisect.bisect_left(self._keys, float("-inf") if min_val is None else min_val)
        max_idx = bisect.bisect_right(self._keys, float("inf") if max_val is None else max_val)


        filtered_keys = self._keys[min_idx:max_idx]
        filtered_values = self._values[min_idx:max_idx]
        return filtered_keys, filtered_values

    def __len__(self):
        return len(self._all_lines)

    def __repr__(self):
        if len(self):
            wl_min, wl_max = self._keys[0], self._keys[-1]
            return (f"<{__name__}.StrongLinesContainer(n_lines={len(self)}, "
                    f"wavelength_range=({wl_min:.2f}, {wl_max:.2f}))>")
        return f"<{__name__}.StrongLinesContainer(empty)>"
