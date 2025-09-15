"""Panel with sampling controls."""

import tkinter as tk
from tkinter import ttk

from tobes_ui.calibration.common import (CalibrationControlPanel, ClampedSpinbox, ToolTip)


class SamplingControl(CalibrationControlPanel):  # pylint: disable=too-many-ancestors
    """Control for sampling."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, text='Sampling', **kwargs)

    def _setup_gui(self):
        """Setup GUI elements for the control."""
        self._initialized = False

        # --- Variables ---
        self._mode = tk.StringVar(value='avg')
        self._mode.trace_add('write', self._change_cb)

        # --- Widgets ---
        self._num_samples_spinbox = ClampedSpinbox(self, label_text='Samples:',
                                                   min_val=1, max_val=10, initial=1,
                                                   on_change=self._change_cb)
        self._num_samples_spinbox.grid(row=0, column=0, columnspan=2, sticky='w', padx=5, pady=2)
        ToolTip(self._num_samples_spinbox, "Number of samples to average")

        avg_radio = ttk.Radiobutton(self, text="Average", variable=self._mode, value='avg')
        ToolTip(avg_radio, "Average the samples")
        max_radio = ttk.Radiobutton(self, text="Max", variable=self._mode, value='max')
        ToolTip(max_radio, "Pick max for each wl from the samples")

        # --- Layout ---
        avg_radio.grid(row=1, column=0, padx=5, pady=2)
        max_radio.grid(row=1, column=1, padx=5, pady=2)

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
                    'samples': self._num_samples_spinbox.get(),
            }
            self.on_change(self._data)
