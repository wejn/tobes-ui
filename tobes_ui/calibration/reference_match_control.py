"""Panel with reference match controls."""

from tobes_ui.calibration.common import (CalibrationControlPanel, ClampedSpinbox, ToolTip)

class ReferenceMatchControl(CalibrationControlPanel):  # pylint: disable=too-many-ancestors
    """Control for reference matching parameters."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, text='Ref. match', **kwargs)

    def _setup_gui(self):
        """Setup GUI elements for the control."""
        self._initialized = False

        # --- Widgets ---
        self._delta_plus_spinbox = ClampedSpinbox(self, label_text="WL Δ [+nm]:",
                                                  min_val=0.0, max_val=20.0, initial=3,
                                                  allow_float=True, increment=0.1,
                                                  on_change=self._change_cb)
        self._delta_minus_spinbox = ClampedSpinbox(self, label_text="WL Δ [-nm]:",
                                                   min_val=0.0, max_val=20.0, initial=3,
                                                   allow_float=True, increment=0.1,
                                                   on_change=self._change_cb)
        self._delta_plus_spinbox.grid(row=0, column=0, sticky='ew', padx=5, pady=2)
        ToolTip(self._delta_plus_spinbox, ("Wavelength Δ (positive) within which to\n" +
                                           "match against reference lines, in nm"))
        self._delta_minus_spinbox.grid(row=1, column=0, sticky='ew', padx=5, pady=2)
        ToolTip(self._delta_minus_spinbox, ("Wavelength Δ (negative) within which to\n" +
                                            "match against reference lines, in nm"))

        self.columnconfigure(0, weight=1)
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
                'delta_plus': self._delta_plus_spinbox.get(),
                'delta_minus': self._delta_minus_spinbox.get(),
            }
            self.on_change(self._data)
