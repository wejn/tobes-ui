"""Wavelength editor form (dialog)."""

import tkinter as tk
from tkinter import ttk
from tkinter.simpledialog import Dialog

import numpy as np

from tobes_ui.calibration.common import ClampedSpinbox


class WavelengthEditor(Dialog):
    """Popup dialog for adding or editing a calibration point."""

    def __init__(self, parent, pixel, valid_pixels, pixel_to_wl, new_wl, reference_lines_lookup,
                 on_change):
        self._pixel = pixel
        self._valid_pixels = valid_pixels
        self._pixel_to_wl = pixel_to_wl
        self._new_wl = new_wl
        self._reference_lines_lookup = reference_lines_lookup
        self._on_change = on_change

        self._reference_lines = []

        super().__init__(parent, title="Edit Wavelength")

    def body(self, master):
        """Create and place widgets in the dialog body."""

        self._new_wl_var = tk.StringVar(master, value=f"{self._new_wl or ''}")

        main_frame = ttk.Frame(master, padding=10)
        main_frame.grid(row=0, column=0, sticky="nsew")

        pixel_spinbox = ClampedSpinbox(parent=main_frame,
                                       min_val=self._valid_pixels[0],
                                       max_val=self._valid_pixels[1],
                                       initial=self._pixel or '',
                                       label_text="Pixel:")
        pixel_spinbox.grid(row=0, column=0, sticky="w")
        if self._valid_pixels[0] == self._valid_pixels[1] and self._pixel:
            pixel_spinbox.disabled = True

        def pixel_change(val):
            self._pixel = val
            update_wavelength()
            update_references()

        pixel_spinbox.on_change = pixel_change

        current_wavelength = ttk.Label(main_frame, text="TBA")
        current_wavelength.grid(row=1, column=0, sticky="w", pady=(0, 10))
        def update_wavelength():
            if self._pixel:
                wavelength = self._pixel_to_wl(self._pixel)
                text = f"Current wavelength: {wavelength:.6f}"
            else:
                text = "Current wavelength: n/a"
            current_wavelength.config(text=text)
        update_wavelength()

        entry_frame = ttk.Frame(main_frame)
        entry_frame.grid(row=2, column=0, sticky="ew", pady=5)
        ttk.Label(entry_frame, text="New Wavelength:").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(entry_frame, textvariable=self._new_wl_var, validate='key',
                               validatecommand=(master.register(self._validate_float), '%P'))
        entry.grid(row=0, column=1, sticky="ew", padx=5)
        entry.icursor(tk.END)

        ref_frame = ttk.LabelFrame(main_frame, text="Nearby Reference Lines", padding=5)
        ref_frame.grid(row=3, column=0, sticky="nsew", pady=10)

        tree_frame = ttk.Frame(ref_frame)
        tree_frame.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")

        columns = ("Δ", "wavelength", "element", "intensity", "flags")
        self._treeview = ttk.Treeview(tree_frame, columns=columns, yscrollcommand=scrollbar.set,
                                      show="", height=5)

        self._treeview.column("Δ", width="30", anchor="e")
        self._treeview.column("wavelength", width="100", anchor="e")
        self._treeview.column("element", width="30", anchor="w")
        self._treeview.column("intensity", width="50", anchor="e")
        self._treeview.column("flags", width="25", anchor="w")

        scrollbar.config(command=self._treeview.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._treeview.grid(row=0, column=0, sticky="nsew")
        ref_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        def update_references():
            self._treeview.delete(*self._treeview.get_children())
            self._reference_lines.clear()

            if self._pixel:
                wavelength = self._pixel_to_wl(self._pixel)
                for line in sorted(self._reference_lines_lookup(wavelength),
                                   key=lambda e: abs(e.wavelength-wavelength)):
                    self._reference_lines.append(line)
                    self._treeview.insert(
                            '',
                            "end",
                            values=[
                                f"{line.wavelength-wavelength:+.2f}",
                                f"{line.wavelength:.6f}",
                                f"{line.element} {'I' * line.ionization}",
                                str(line.intensity),
                                str(line.raw_flags),
                                ])
        update_references()

        self._treeview.bind("<<TreeviewSelect>>", self._on_treeview_select)
        self._treeview.bind("<Double-1>", self.ok)

        master.grid_rowconfigure(0, weight=1)
        master.grid_rowconfigure(1, weight=1)
        master.grid_rowconfigure(2, weight=1)
        master.grid_rowconfigure(3, weight=1)

        if self._pixel:
            return entry
        else:
            return pixel_spinbox.spinbox()

    def _validate_float(self, value_if_allowed):
        """Validation command for the entry widget."""
        if value_if_allowed == "":
            return True
        try:
            float(value_if_allowed)
            return True
        except ValueError:
            return False

    def _on_treeview_select(self, _event):
        """Handle selection from the reference lines treeview."""
        selection = self._treeview.selection()
        if not selection:
            return

        idx = self._treeview.index(selection[0])
        if not 0 <= idx < len(self._reference_lines):
            return

        self._new_wl_var.set(self._reference_lines[idx].wavelength)

    def validate(self):
        """Validate that the pixel and the value are both correct."""
        try:
            int(self._pixel)
            float(self._new_wl_var.get())
        except (ValueError, TypeError):
            return False
        return True

    def apply(self):
        """Handle OK button press (called by Dialog when OK is clicked)."""
        try:
            new_wl = float(self._new_wl_var.get())
            self._on_change(self._pixel, new_wl)
        except ValueError:
            pass

if __name__ == "__main__":
    from tobes_ui.strong_lines import STRONG_LINES
    from tobes_ui.strong_lines_container import StrongLinesContainer

    def test_cb(pixel, new_wavelength):
        """Callback function to handle the edited wavelength."""
        print(f"pixel: {pixel}, wavelength: {new_wavelength:.4f}")

    def main():
        """Main function to test the popup."""
        root = tk.Tk()
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.bind('<Escape>', lambda event: root.destroy())

        root.grid_columnconfigure(0, weight=1)

        root.geometry("400x300")
        ttk.Label(root, text="This is the main window with some dummy content.").grid(
                row=0, column=0, pady=10)

        strong_lines_container = StrongLinesContainer(
                {k: v.persistent_lines for k, v in STRONG_LINES.items()})
        ref_delta = 3  # +- 3nm

        # new
        pixel = 678
        pixels = (20, 2047)
        new_wl = 589.1234

        def pixel_to_wl(pixel):
            polyfit = np.array([-1.107232e-09, -2.100606e-05, 0.380489, 341.20639])
            return np.polyval(polyfit, pixel)

        def ref_lines(cur_wl):
            return strong_lines_container.find_in_range(cur_wl - ref_delta, cur_wl + ref_delta)

        ttk.Button(root,
                   text="Open Add Wavelength Dialog (no pxl)",
                   command=lambda: WavelengthEditor(root, None, pixels, pixel_to_wl, None,
                                                    ref_lines, test_cb)).grid(
                                                            row=1, column=0, pady=10)

        ttk.Button(root,
                   text="Open Edit Wavelength Dialog",
                   command=lambda: WavelengthEditor(root, pixel, pixels, pixel_to_wl, new_wl,
                                                    ref_lines, test_cb)).grid(
                                                            row=2, column=0, pady=10)

        ttk.Button(root,
                   text="Open Edit Wavelength Dialog (fixed)",
                   command=lambda: WavelengthEditor(root, pixel, [pixel, pixel], pixel_to_wl,
                                                    new_wl, ref_lines, test_cb)).grid(
                                                            row=3, column=0, pady=10)

        ttk.Button(root, text="Quit", command=root.destroy).grid(row=4, column=0, pady=10)

        root.mainloop()

    main()
