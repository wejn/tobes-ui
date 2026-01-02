"""Strong lines control UI."""

# pylint: disable=too-many-ancestors,too-many-instance-attributes

import tkinter as tk
from tkinter import ttk

from tobes_ui.strong_lines import STRONG_LINES
from tobes_ui.calibration.common import (CalibrationControlPanel, ClampedSpinbox, ToolTip)

class StrongLinesControl(CalibrationControlPanel):
    """Control panel for strong lines."""

    def __init__(self, parent, max_cols=5, on_change=None, **kwargs):
        self.on_change = on_change
        self._max_cols = max(1, max_cols)
        self._vars = {}
        self._checkboxes = {}

        super().__init__(parent, text='Strong lines', **kwargs)

    def _setup_gui(self):
        self._all_checkboxes = ttk.Frame(self)
        self._all_checkboxes.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        ToolTip(self._all_checkboxes, "Element(s) to enable strong lines for")

        row = 0
        for idx, elem in enumerate(STRONG_LINES.keys()):
            if idx % self._max_cols == 0:
                row += 1
            self._vars[elem] = tk.BooleanVar(value=False)
            self._checkboxes[elem] = ttk.Checkbutton(self._all_checkboxes, text=elem,
                                                     variable=self._vars[elem],
                                                     command=lambda e=elem: self._change_cb(e))
            self._checkboxes[elem].grid(column=idx%self._max_cols, row=row, sticky="news")
            self._all_checkboxes.columnconfigure(idx%self._max_cols, weight=1)

        self._sep = ttk.Separator(self, orient='horizontal')
        self._sep.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)

        self._persistent_only = tk.BooleanVar(value=False)
        self._po_cbox = ttk.Checkbutton(self, text='Persistent only',
                                        variable=self._persistent_only, command=self._change_cb)
        self._po_cbox.grid(row=2, column=0, columnspan=2)
        ToolTip(self._po_cbox, "Use only persistent lines of the selected element(s)")

        self._intensity = ClampedSpinbox(parent=self, min_val=0, max_val=1000,
                                         label_text="Min. intensity:", increment=50)
        self._intensity.on_change = lambda val: self._change_cb()
        self._intensity.grid(row=3, column=0, columnspan=2)
        ToolTip(self._intensity, "Minimal intensity of the strong lines to select (0..1000)")

        self._ionization_1 = tk.BooleanVar(value=True)
        self._io1_cbox = ttk.Checkbutton(self, text='Ionization I',
                                         variable=self._ionization_1, command=self._change_cb)
        self._ionization_2 = tk.BooleanVar(value=False)
        self._io2_cbox = ttk.Checkbutton(self, text='Ionization II',
                                         variable=self._ionization_2, command=self._change_cb)
        self._io1_cbox.grid(row=4, column=0, sticky="w", padx=(5,0))
        ToolTip(self._io1_cbox, "Show lines related to first level of ionization")
        self._io2_cbox.grid(row=4, column=1, sticky="e", padx=(0,5))
        ToolTip(self._io2_cbox, "Show lines related to second level of ionization")



    def _change_cb(self, element=None):
        """Change callback, for individual elements (or all when None)."""
        min_int = self._intensity.get()
        pers_only = self._persistent_only.get()
        def sl_find(elem):
            ionization = [1 if self._ionization_1.get() else -1,
                          2 if self._ionization_2.get() else -1]
            sls = STRONG_LINES[elem].for_intensity_range(range(min_int,1000), pers_only)
            return [sl for sl in sls if sl.ionization in ionization]

        if element is not None:
            if self._vars[element].get():
                self._data[element] = sl_find(element)
            else:
                self._data.pop(element)
        else:
            self._data = {k: sl_find(k) for k, v in self._vars.items() if v.get()}

        if self._on_change:
            self._on_change(self._data)
