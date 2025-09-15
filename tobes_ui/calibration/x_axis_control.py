"""Panel with X axis controls."""

import tkinter as tk
from tkinter import ttk

from tobes_ui.calibration.common import (CalibrationControlPanel, ClampedSpinbox, ToolTip)


class XAxisControl(CalibrationControlPanel):  # pylint: disable=too-many-ancestors
    """Control for X-axis display mode."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, text='X-Axis', **kwargs)

    def _setup_gui(self):
        """Setup GUI elements for the control."""
        self._initialized = False
        self._mode = tk.StringVar(value='init')

        # --- Widgets ---
        old_radio = ttk.Radiobutton(self, text="Initial calibration", variable=self._mode,
                                    value='init')
        ToolTip(old_radio, "Use initial calibration for X axis")
        new_radio = ttk.Radiobutton(self, text="New calibration", variable=self._mode, value='new',
                                    state='disabled')  # FIXME: enable when new cali is available
        ToolTip(new_radio, "Use new (currently setup) calibration for X axis")
        fixed_radio = ttk.Radiobutton(self, text="Fixed:", variable=self._mode, value='fixed')
        ToolTip(fixed_radio, ("Use fixed min..max for X axis;\n" +
                              "(beware that first few px are optical dark)"))

        fixed_widgets_frame = ttk.Frame(self)
        # FIXME: this might need floats, not ints
        self._fixed_min_spinbox = ClampedSpinbox(fixed_widgets_frame, min_val=200, max_val=1100,
                                                 initial=380, on_change=self._change_cb)
        self._fixed_max_spinbox = ClampedSpinbox(fixed_widgets_frame, min_val=200, max_val=1100,
                                                 initial=780, on_change=self._change_cb)
        self._fixed_min_spinbox.pack(side=tk.LEFT)
        ToolTip(self._fixed_min_spinbox, "Min for X axis (for first pixel)")

        ttk.Label(fixed_widgets_frame, text="..").pack(side=tk.LEFT, padx=2)

        self._fixed_max_spinbox.pack(side=tk.LEFT)
        ToolTip(self._fixed_max_spinbox, "Max for X axis (for last pixel)")

        # --- Layout ---
        old_radio.grid(row=0, column=0, sticky='w', padx=5, pady=2, columnspan=2)
        new_radio.grid(row=1, column=0, sticky='w', padx=5, pady=2, columnspan=2)
        fixed_radio.grid(row=2, column=0, sticky='w', padx=5, pady=2)
        fixed_widgets_frame.grid(row=2, column=1, sticky='w', padx=5, pady=2)

        self.columnconfigure(1, weight=1)

        # --- Enable/disable logic ---
        def _toggle_enabled_state(*_args):
            is_fixed = self._mode.get() == 'fixed'
            for spinbox_frame in [self._fixed_min_spinbox, self._fixed_max_spinbox]:
                for child in spinbox_frame.winfo_children():
                    try:
                        child.config(state=tk.NORMAL if is_fixed else tk.DISABLED)
                    except tk.TclError:
                        pass
            self._change_cb()
        self._mode.trace_add('write', _toggle_enabled_state)

        self._initialized = True
        _toggle_enabled_state()  # Set initial state & trigger first callback

    def _change_cb(self, *_args):
        """Callback for when any control value changes."""
        if not self._initialized:
            self._data = {}
            return
        if self.on_change:
            mode = self._mode.get()
            if mode == 'fixed':
                self._data = {
                        'mode': 'fixed',
                        'min': self._fixed_min_spinbox.get(),
                        'max': self._fixed_max_spinbox.get(),
                }
            else:
                self._data = {
                        'mode': mode,
                }
            self.on_change(self._data)
