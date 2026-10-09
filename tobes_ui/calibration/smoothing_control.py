"""Panel with smoothing controls."""

import tkinter as tk
from tkinter import ttk

from tobes_ui.calibration.common import (CalibrationControlPanel, ClampedSpinbox, ToolTip)


class SmoothingControl(CalibrationControlPanel):  # pylint: disable=too-many-ancestors
    """Control for smoothing."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, text='Smoothing', **kwargs)

    def _setup_gui(self):
        """Setup GUI elements for the control."""
        self._initialized = False

        # --- Variables ---
        self._mode = tk.StringVar(value='boxcar')
        self._mode.trace_add('write', self._change_cb)

        # --- Widgets ---
        self._width_spinbox = ClampedSpinbox(self, label_text='Width:',
                                             min_val=0, max_val=20, initial=0,
                                             on_change=self._change_cb)
        self._width_spinbox.grid(row=0, column=0, columnspan=3, sticky='w', padx=5, pady=2)
        ToolTip(self._width_spinbox, "Width for the smoothing")

        w = "\n(width is num pixels on each side)"

        box_radio = ttk.Radiobutton(self, text="Box", variable=self._mode, value='boxcar')
        ToolTip(box_radio, "Boxcar (uniform)" + w)
        tri_radio = ttk.Radiobutton(self, text="Tri", variable=self._mode, value='triangular')
        ToolTip(tri_radio, "Triangular (Bartlett)" + w)
        gau_radio = ttk.Radiobutton(self, text="Gau", variable=self._mode, value='gaussian')
        ToolTip(gau_radio, "Gaussian" + w)

        # --- Layout ---
        box_radio.grid(row=1, column=0, padx=5, pady=2)
        tri_radio.grid(row=1, column=1, padx=5, pady=2)
        gau_radio.grid(row=1, column=2, padx=5, pady=2)

        self._initialized = True
        self._change_cb()  # Set initial state & trigger first callback

    def _change_cb(self, *_args):
        """Callback for when any control value changes."""
        if not self._initialized:
            self._data = {}
            return
        if self.on_change:
            self._data = {
                    'mode': self._mode.get(),
                    'width': self._width_spinbox.get(),
            }
            self.on_change(self._data)
