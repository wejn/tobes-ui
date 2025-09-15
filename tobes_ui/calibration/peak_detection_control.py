"""Panel with peak detection controls."""

from tobes_ui.calibration.common import (CalibrationControlPanel, ClampedSpinbox, ToolTip)


class PeakDetectionControl(CalibrationControlPanel):  # pylint: disable=too-many-ancestors
    """Control for peak detection parameters."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, text='Peak detection', **kwargs)

    def _setup_gui(self):
        """Setup GUI elements for the control."""
        self._initialized = False

        # --- Widgets ---
        self._prominence_spinbox = ClampedSpinbox(self, label_text="Prominence [%]:",
                                                  min_val=1, max_val=100, initial=50,
                                                  on_change=self._change_cb)
        self._prominence_spinbox.grid(row=0, column=0, sticky='ew', padx=5, pady=2)
        ToolTip(self._prominence_spinbox, "Requisite peak prominence, in %")

        self._distance_spinbox = ClampedSpinbox(self, label_text="Distance [px]:",
                                                min_val=1, max_val=50, initial=15,
                                                on_change=self._change_cb)
        self._distance_spinbox.grid(row=1, column=0, sticky='ew', padx=5, pady=2)
        ToolTip(self._distance_spinbox, "Distance between peaks, in pixels")

        self._window_length_spinbox = ClampedSpinbox(self, label_text="Window:",
                                                     min_val=3, max_val=50, initial=20,
                                                     on_change=self._change_cb)
        self._window_length_spinbox.grid(row=2, column=0, sticky='ew', padx=5, pady=2)
        ToolTip(self._window_length_spinbox, "Window length within which to detect peaks")

        self.columnconfigure(0, weight=1)

        self._initialized = True
        self._change_cb()  # Set initial state & trigger first callback

    def _change_cb(self, *_args):
        """Callback for when any control value changes."""
        if not self._initialized:
            self._data = {}
            return
        if self.on_change:
            self._data = {
                'prominence': self._prominence_spinbox.get(),
                'distance': self._distance_spinbox.get(),
                'window_length': self._window_length_spinbox.get()
            }
            self.on_change(self._data)
