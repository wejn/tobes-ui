"""Panel with integration controls."""

import tkinter as tk
from tkinter import ttk

from tobes_ui.calibration.common import (CalibrationControlPanel, ClampedSpinbox, ToolTip)


class IntegrationControl(CalibrationControlPanel):  # pylint: disable=too-many-ancestors
    """Integration time control."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, text='Integration', **kwargs)

    def _setup_gui(self):
        """Setup GUI elements for the control."""
        self._initialized = False
        self._mode = tk.StringVar(value='auto')
        self._integration_time_var = tk.StringVar(value='n/a')  # FIXME: plug this in

        # --- Widgets ---
        auto_radio = ttk.Radiobutton(self, text="Auto", variable=self._mode, value='auto')
        ToolTip(auto_radio, "Automatically determine integration period (within bounds)")
        manual_radio = ttk.Radiobutton(self, text="Manual", variable=self._mode, value='manual')
        ToolTip(manual_radio, "Manually set integration period")

        auto_widgets_frame = ttk.Frame(self)
        self._auto_min_spinbox = ClampedSpinbox(auto_widgets_frame, min_val=1, max_val=65535,
                                                initial=1, on_change=self._change_cb)
        self._auto_max_spinbox = ClampedSpinbox(auto_widgets_frame, min_val=1, max_val=65535,
                                                initial=1000, on_change=self._change_cb)

        self._auto_min_spinbox.pack(side=tk.LEFT)
        ToolTip(self._auto_min_spinbox, "Min integration period [ms]")

        ttk.Label(auto_widgets_frame, text="..").pack(side=tk.LEFT, padx=2)

        self._auto_max_spinbox.pack(side=tk.LEFT)
        ToolTip(self._auto_max_spinbox, "Max integration period [ms]")

        manual_widgets_frame = ttk.Frame(self)
        self._manual_value_spinbox = ClampedSpinbox(manual_widgets_frame, min_val=1, max_val=65535,
                                                    initial=100, on_change=self._change_cb)
        self._manual_value_spinbox.pack(side=tk.LEFT)
        ToolTip(self._manual_value_spinbox, "Integration period [ms]")

        self._integration_time_label = ttk.Label(manual_widgets_frame,
                                                 textvariable=self._integration_time_var)
        self._integration_time_label.pack(side=tk.RIGHT, padx=(5,0))
        ToolTip(self._integration_time_label,
                "Current integration period [ms].\nClick to copy to manual.")
        self._integration_time_label.bind("<Button-1>", self._on_integration_time_click)

        # --- Layout ---
        auto_radio.grid(row=0, column=0, sticky='w', padx=5, pady=2)
        auto_widgets_frame.grid(row=0, column=1, sticky='w', padx=5, pady=2)
        manual_radio.grid(row=1, column=0, sticky='w', padx=5, pady=2)
        manual_widgets_frame.grid(row=1, column=1, sticky='we', padx=5, pady=2)

        # --- Enable/disable logic ---
        def _toggle_enabled_state(*_args):
            is_auto = self._mode.get() == 'auto'
            for spinbox_frame in [self._auto_min_spinbox, self._auto_max_spinbox]:
                for child in spinbox_frame.winfo_children():
                    try:
                        child.config(state=tk.NORMAL if is_auto else tk.DISABLED)
                    except tk.TclError:
                        pass
            for child in self._manual_value_spinbox.winfo_children():
                try:
                    child.config(state=tk.DISABLED if is_auto else tk.NORMAL)
                except tk.TclError:
                    pass
            self._change_cb()
        self._mode.trace_add('write', _toggle_enabled_state)

        self._initialized = True
        _toggle_enabled_state()  # Set initial state & trigger first callback

    def _on_integration_time_click(self, _event):
        """Handle click on current integration time label."""
        current_time_str = self._integration_time_var.get()
        if current_time_str.isdigit():
            current_time = int(current_time_str)
            self._mode.set('manual')
            self._manual_value_spinbox.set(current_time)

    def _change_cb(self, *_args):
        """Callback for when any control value changes."""
        if not self._initialized:
            self._data = {}
            return
        if self.on_change:
            mode = self._mode.get()
            if mode == 'auto':
                self._data = {
                        'mode': 'auto',
                        'min': self._auto_min_spinbox.get(),
                        'max': self._auto_max_spinbox.get(),
                }
            else:
                self._data = {
                        'mode': 'manual',
                        'value': self._manual_value_spinbox.get(),
                }
            self.on_change(self._data)
