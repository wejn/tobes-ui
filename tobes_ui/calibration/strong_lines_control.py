"""Strong lines control UI."""

# pylint: disable=too-many-ancestors,too-many-instance-attributes

import tkinter as tk
from tkinter import ttk

from tobes_ui.strong_lines import STRONG_LINES
from tobes_ui.calibration.common import (ClampedSpinbox, ToolTip)

class StrongLinesControl(ttk.LabelFrame):
    """Control panel for strong lines."""

    def __init__(self, parent, max_cols=5, on_change=None, **kwargs):
        super().__init__(parent, text='Strong lines', pad=5, **kwargs)

        self._on_change = on_change
        self._vars = {}
        self._checkboxes = {}
        self._strong_lines = {}

        self._setup_gui(max(1, max_cols))

    def _setup_gui(self, max_cols):
        self._all_checkboxes = ttk.Frame(self)
        self._all_checkboxes.pack(fill=tk.BOTH, expand=True)
        ToolTip(self._all_checkboxes, "Element(s) to enable strong lines for")

        row = 0
        for idx, elem in enumerate(STRONG_LINES.keys()):
            if idx % max_cols == 0:
                row += 1
            self._vars[elem] = tk.BooleanVar(value=False)
            self._checkboxes[elem] = ttk.Checkbutton(self._all_checkboxes, text=elem,
                                                     variable=self._vars[elem],
                                                     command=lambda e=elem: self._change_cb(e))
            self._checkboxes[elem].grid(column=idx%max_cols, row=row, sticky="news")
            self._all_checkboxes.columnconfigure(idx%max_cols, weight=1)

        self._sep = ttk.Separator(self, orient='horizontal')
        self._sep.pack(fill='x', pady=5)

        self._persistent_only = tk.BooleanVar(value=False)
        self._po_cbox = ttk.Checkbutton(self, text='Persistent only',
                                        variable=self._persistent_only, command=self._change_cb)
        self._po_cbox.pack()
        ToolTip(self._po_cbox, "Use only persistent lines of the selected element(s)")

        self._intensity = ClampedSpinbox(parent=self, min_val=0, max_val=1000,
                                         label_text="Min. intensity:")
        self._intensity.on_change = lambda val: self._change_cb()
        self._intensity.pack()
        ToolTip(self._intensity, "Minimal intensity of the strong lines to select (0..1000)")

    @property
    def on_change(self):
        "Getter for on_change."""
        return self._on_change

    @on_change.setter
    def on_change(self, proc):
        "Setter for on_change."""
        self._on_change = proc

    @property
    def strong_lines(self):
        """Getter for strong_lines; that's what on_change emits."""
        return self._strong_lines

    def _change_cb(self, element=None):
        """Change callback, for individual elements (or all when None)."""
        min_int = self._intensity.get()
        pers_only = self._persistent_only.get()
        def sl_find(elem):
            return STRONG_LINES[elem].for_intensity_range(range(min_int,1000), pers_only)

        if element is not None:
            if self._vars[element].get():
                self._strong_lines[element] = sl_find(element)
            else:
                self._strong_lines.pop(element)
        else:
            self._strong_lines = {k: sl_find(k) for k, v in self._vars.items() if v.get()}

        if self._on_change:
            self._on_change(self._strong_lines)
