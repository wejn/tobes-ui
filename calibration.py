#!/usr/bin/env python3
"""Calibration for Ocean Optics spectrometer"""

from dataclasses import dataclass
from datetime import datetime
import queue
import pprint
import sys
import textwrap
import tkinter as tk
from tkinter import ttk


import numpy as np
from scipy.interpolate import interp1d
import seabreeze.spectrometers as sb
import matplotlib.pyplot as plt

from tobes_ui.strong_lines import STRONG_LINES


class ToolTip:
    """Tool tip widget for arbitrary Tk element."""

    def __init__(self, widget, text, delay=500, above=False):
        self.widget = widget
        self.text = text
        self.delay = delay  # milliseconds
        self.tooltip = None
        self.after_id = None
        self.above = above

        self.widget.bind("<Enter>", self.schedule)
        self.widget.bind("<Leave>", self.hide_tooltip)
        self.widget.bind("<Motion>", self.move)  # update position if mouse moves

    def schedule(self, _event=None):
        """Schedule showing the tooltip after a delay."""
        self.after_id = self.widget.after(self.delay, self.show_tooltip)

    def show_tooltip(self):
        """Actually create and display the tooltip."""
        if self.tooltip:
            return  # already showing

        x = self.widget.winfo_rootx() + 20
        if self.above:
            y = self.widget.winfo_rooty() - self.widget.winfo_height() - 5 # FIXME
        else:
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            self.tooltip,
            text=str(self.text()) if callable(self.text) else str(self.text),
            background="white",
            justify="left",
            relief="solid",
            borderwidth=1,
            padx=5,
            pady=3
        )
        label.pack()

    def hide_tooltip(self, _event=None):
        """Cancel schedule and hide tooltip if visible."""
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def move(self, _event):
        """Optional: reschedule if the mouse moves inside the widget."""
        if self.tooltip is None and self.after_id is None:
            if self.after_id is not None:
                self.widget.after_cancel(self.after_id)
                self.after_id = None
            self.schedule()


class TracedStringVar(tk.StringVar):
    """String var that has onchange handler."""

    def __init__(self, value="", on_change=None):
        super().__init__(value=value)
        self._old = value
        self._on_change = on_change
        self.trace_add("write", self._change_cb)

    @property
    def on_change(self):
        "Getter for on_change."""
        return self._on_change

    @on_change.setter
    def on_change(self, proc):
        "Setter for on_change."""
        self._on_change = proc

    def _change_cb(self, *args):
        """Change callback, to be executed when value changes."""
        new = self.get()
        if new != self._old:
            self._old = new
            if self._on_change:
                self._on_change(*args)


class ClampedSpinbox(ttk.Frame):
    """Spinbox that holds an integer clamped to min_val, max_val range (inclusive)."""

    def __init__(self, parent, min_val=0, max_val=10, initial=None, label_text="", on_change=None,
                 **kwargs):
        super().__init__(parent, **kwargs)

        self.min_val = min_val
        self.max_val = max_val
        self._on_change = on_change
        self._value_var = TracedStringVar(value=str(initial if initial is not None else min_val))
        self._value_var.on_change = self._change_cb

        ttk.Label(self, text=label_text).pack(side="left")

        self._spinbox = ttk.Spinbox(
            self,
            from_=self.min_val,
            to=self.max_val,
            textvariable=self._value_var,
            validate="key",
            validatecommand=(self.register(self._validate), "%P"),
            width=max(len(str(min_val)), len(str(max_val))),
            command=lambda: self._clamp(lose_focus=True)
        )
        self._spinbox.pack(side="right", padx=(5, 0))

        # Bind arrow changes to update label
        self._spinbox.bind("<FocusOut>", lambda e: self._clamp())
        self._spinbox.bind("<Return>", lambda e: self._clamp(lose_focus=True))

    @property
    def on_change(self):
        "Getter for on_change."""
        return self._on_change

    @on_change.setter
    def on_change(self, proc):
        "Setter for on_change."""
        self._on_change = proc

    def _validate(self, new_value):
        """Per-keystroke validation."""
        if new_value == "":
            return True
        if new_value.isdigit():
            value = int(new_value)
            if value < self.min_val:
                self._value_var.set(str(self.min_val))
                self._spinbox.selection_clear()
                self._spinbox.icursor(tk.END)
                return False
            if value > self.max_val:
                self._value_var.set(str(self.max_val))
                self._spinbox.selection_clear()
                self._spinbox.icursor(tk.END)
                return False
            return True
        return False

    def _clamp(self, lose_focus=False):
        """Clamp value on focus out or Enter."""
        if lose_focus:
            self.focus()
        value = max(self.min_val, min(self.max_val, self.get()))
        self._value_var.set(str(value))
        self._spinbox.selection_clear()
        self._spinbox.icursor(tk.END)

    def _change_cb(self, *args):
        """Change callback, to be executed when spinbox changes."""
        if self._on_change:
            self._on_change(self.get())

    def get(self):
        """Return current integer value."""
        try:
            return int(self._value_var.get())
        except ValueError:
            return self.min_val

    def set(self, value):
        """Set value programmatically (clamped)."""
        value = max(self.min_val, min(self.max_val, int(value)))
        self._value_var.set(str(value))


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
        def sl_find(e):
            return STRONG_LINES[e].for_intensity_range(range(min_int,1000), pers_only)

        if element is not None:
            if self._vars[element].get():
                self._strong_lines[element] = sl_find(element)
            else:
                self._strong_lines.pop(element)
        else:
            self._strong_lines = {k: sl_find(k) for k, v in self._vars.items() if v.get()}

        if self._on_change:
            self._on_change(self._strong_lines)


class CalibrationGUI:
    """GUI for Ocean spectrometer wavelength calibration."""

    def __init__(self, root, spectrometer, initial_polyfit):
        self._root = root
        self._root.title("Wavelength Calibration")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        #self._root.geometry("1024x768")
        #self._root.minsize(800, 600)

        self._spectrometer = spectrometer
        self._capturing = False
        self._worker_thread = None
        self._data_queue = queue.Queue()

        self._initial_polyfit = np.array(initial_polyfit)

        self._status_label = None

        # FIXME: rest of the data

        self._setup_ui()

        # debug info
        w = self._root.winfo_reqwidth()
        h = self._root.winfo_reqheight()
        print(f'window: {w}x{h}')
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        print(f"Primary display size: {screen_width}x{screen_height}")

    def _setup_ui(self):
        paned_window = tk.PanedWindow(self._root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        paned_window.pack(fill=tk.BOTH, expand=True)

        left_frame = self._setup_left_frame(paned_window)
        right_frame = self._setup_right_frame(paned_window)

        paned_window.add(left_frame)
        paned_window.add(right_frame)

        # resize left to min(left minwidth, 30%)
        def pw_on_resize(_event):
            total_width = paned_window.winfo_width()
            paned_window.paneconfig(left_frame, minsize=left_frame.winfo_reqwidth())
            paned_window.paneconfig(right_frame, minsize=right_frame.winfo_reqwidth())
            paned_window.sash_place(0, min(left_frame.winfo_reqwidth(), int(total_width * 0.3)), 0)
            # FIXME: ^^ probably doesn't work as I would expect...
        paned_window.bind('<Configure>', pw_on_resize)

    def _setup_left_frame(self, parent):
        left_frame = ttk.Frame(parent)

        table_frame = ttk.Frame(left_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        poly_label = ttk.Label(table_frame, text="Pixels")
        poly_label.pack()

        # Create treeview for table
        columns = ('pixel', 'wl', 'new_wl')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=16)

        # Define headings
        tree.heading('pixel', text='pixel')
        tree.heading('wl', text='wl')
        tree.heading('new_wl', text='new_wl')

        # Configure column widths
        tree.column('pixel', width=60, anchor='e')
        tree.column('wl', width=80, anchor='e')
        tree.column('new_wl', width=80, anchor='e')

        # Scrollbar for table
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        tree.insert('', 'end', values=('1', '1', '1'))
        tree.insert('', 'end', values=('2', '2', '2'))
        tree.insert('', 'end', values=('3', '3', '3'))

        # Bind events # FIXME
        #tree.bind('<Double-1>', self.on_table_double_click)
        #tree.bind('<Delete>', self.on_table_delete)
        #tree.bind('<KeyPress-Delete>', self.on_table_delete)

        # Polynomial fit
        poly_frame = ttk.Frame(left_frame, height=200)
        poly_frame.pack(fill=tk.X, padx=5, pady=5)
        poly_frame.pack_propagate(False)

        poly_label = ttk.Label(poly_frame, text="Polynomial Fit")
        poly_label.pack()

        poly_table_frame = ttk.Frame(poly_frame)
        poly_table_frame.pack(fill=tk.BOTH, expand=True)

        poly_columns = ('parameter', 'initial', 'current')
        poly_tree = ttk.Treeview(poly_table_frame, columns=poly_columns, show='headings', height=6)

        poly_tree.heading('parameter', text='Param')
        poly_tree.heading('initial', text='Initial')
        poly_tree.heading('current', text='Current')

        poly_tree.column('parameter', width=30, anchor='w')
        poly_tree.column('initial', width=80, anchor='e')
        poly_tree.column('current', width=80, anchor='e')

        poly_tree.pack(fill=tk.BOTH, expand=True)

        #self.init_poly_table() # FIXME
        parameters = [
            ('X⁰', f"{self._initial_polyfit[3]:.6f}"),
            ('X¹', f"{self._initial_polyfit[2]:.6f}"),
            ('X²', f"{self._initial_polyfit[1]:.6f}"),
            ('X³', f"{self._initial_polyfit[0]:.6f}"),
            ('R²', "-"),
            ('Serr', "-")
        ]
        for param, initial_val in parameters:
            poly_tree.insert('', 'end', values=(param, initial_val, '-'))

        # Controls
        controls_frame = ttk.Frame(left_frame)
        controls_frame.pack(fill=tk.X, padx=5, pady=5)
        capture_button = ttk.Button(controls_frame, text="Capture", command=lambda: print('capt'))
        # FIXME: action ^^
        capture_button.pack(side=tk.LEFT, padx=5)
        save_button = ttk.Button(controls_frame, text="Save Cali",
                                 command=lambda: print('save'), state='disabled')
        # FIXME: action ^^
        save_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(controls_frame, text="Quit", command=self._on_close).pack(side=tk.RIGHT, padx=5)

        # Strong lines
        slc = StrongLinesControl(left_frame)
        slc.on_change = lambda sl: pprint.pprint(
                {k: len([[vv.wavelength, vv.raw_flags] for vv in v]) for k,v in sl.items()})
        # FIXME: something more useful?
        slc.pack(fill="x", padx=5)

        status_frame = ttk.LabelFrame(left_frame, height=90, text='Status')
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        status_frame.pack_propagate(False)

        self._status_label = ttk.Label(status_frame, text="", justify=tk.LEFT, anchor='nw')
        self._status_label.pack(fill=tk.BOTH, expand=True, padx=5)
        self._update_status('Initializing...')
        ToolTip(self._status_label,
                text=lambda: 'Status:\n' + self._status_label.cget('text'), above=True)

        return left_frame

    def _setup_right_frame(self, parent):
        right_frame = ttk.Frame(parent)

        label = ttk.Label(right_frame, text="Right Panel\n(natural width)") # FIXME: rm
        label.pack()

        return right_frame

    def _update_status(self, message):
        if self._status_label:
            self._status_label.config(text=message)
        else:
            print('Status:', message)

    def _on_close(self):
        if self._capturing:
            self._capturing = False
            if self.worker_thread:
                self.worker_thread.join()
        self._root.destroy()

if __name__ == "__main__":
    def main():
        """Zee main(), like in C"""
        try:
            #spectrometer = sb.Spectrometer.from_first_available() # FIXME
            spectrometer = None
        except Exception: # pylint: disable=broad-exception-caught
            print("No spectrometer available")
            sys.exit(1)

        # read wavelength calibration: [a3, a2, a1, a0] for polynomial a3*x^3 + a2*x^2 + a1*x + a0
        def read_wlc(spec):
            coeffs = []
            # Slots 1-4 are wavelength calibration
            for i in range(1, 5):
                try:
                    # For some reason this can be empty
                    coeffs.append(float(spec.f.eeprom.eeprom_read_slot(i).split(b'\x00')[0]))
                except (ValueError, IndexError):
                    coeffs.append(0.0)
            # a0, a1, a2, a3 -> a3, a2, a1, a0
            return coeffs[::-1]

        #wlc = read_wlc(spectrometer) # FIXME
        wlc = [0, 0, 1, 0]
        print("Read initial wavelength calibration coefficients:", wlc)

        root = tk.Tk()
        CalibrationGUI(root, spectrometer, initial_polyfit=wlc)
        root.mainloop()

    main()
