"""Wavelength editor form (dialog)."""

import tkinter as tk
from tkinter import ttk
from tkinter.simpledialog import Dialog

class WavelengthEditor(Dialog):
    """Popup dialog for adding or editing a calibration point."""

    def __init__(self, parent, pixel, current_wl, new_wl, reference_lines, on_change):
        self._pixel = pixel
        self._current_wl = current_wl
        self._new_wl = new_wl or current_wl
        self._reference_lines = reference_lines
        self._on_change = on_change
        super().__init__(parent, title="Edit Wavelength")

    def body(self, master):
        """Create and place widgets in the dialog body."""

        self._new_wl_var = tk.StringVar(master, value=f"{self._new_wl}")

        main_frame = ttk.Frame(master, padding=10)
        main_frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(main_frame, text=f"Pixel: {self._pixel}").grid(row=0, column=0, sticky="w")
        ttk.Label(main_frame, text=f"Current Wavelength: {self._current_wl}").grid(
                row=1, column=0, sticky="w", pady=(0, 10))

        entry_frame = ttk.Frame(main_frame)
        entry_frame.grid(row=2, column=0, sticky="ew", pady=5)
        ttk.Label(entry_frame, text="New Wavelength:").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(entry_frame, textvariable=self._new_wl_var, validate='key',
                               validatecommand=(master.register(self._validate_float), '%P'))
        entry.grid(row=0, column=1, sticky="ew", padx=5)
        entry.icursor(tk.END)

        if self._reference_lines:
            ref_frame = ttk.LabelFrame(main_frame, text="Nearby Reference Lines", padding=5)
            ref_frame.grid(row=3, column=0, sticky="nsew", pady=10)

            list_frame = ttk.Frame(ref_frame)
            list_frame.grid(row=0, column=0, sticky="nsew")
            scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
            self._listbox = tk.Listbox(list_frame,
                                      yscrollcommand=scrollbar.set,
                                      height=min(len(self._reference_lines), 5))
            scrollbar.config(command=self._listbox.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            self._listbox.grid(row=0, column=0, sticky="nsew")
            ref_frame.grid_columnconfigure(0, weight=1)
            list_frame.grid_columnconfigure(0, weight=1)
            list_frame.grid_rowconfigure(0, weight=1)

            for line in self._reference_lines:
                # FIXME: Convert the listbox to Treeview, it will look nicer
                self._listbox.insert("end", str(line))
            self._listbox.bind("<<ListboxSelect>>", self._on_list_select)
            self._listbox.bind("<Double-1>", self.ok)

        master.grid_rowconfigure(0, weight=1)
        master.grid_rowconfigure(1, weight=1)
        master.grid_rowconfigure(2, weight=1)
        master.grid_rowconfigure(3, weight=1)

        return entry

    def _validate_float(self, value_if_allowed):
        """Validation command for the entry widget."""
        if value_if_allowed == "":
            return True
        try:
            float(value_if_allowed)
            return True
        except ValueError:
            return False

    def _on_list_select(self, _event):
        """Handle selection from the reference lines listbox."""
        selection_indices = self._listbox.curselection()
        if not selection_indices:
            return
        if not 0 <= selection_indices[0] < len(self._reference_lines):
            return
        self._new_wl_var.set(self._reference_lines[selection_indices[0]].wavelength)

    def apply(self):
        """Handle OK button press (called by Dialog when OK is clicked)."""
        try:
            new_wl = float(self._new_wl_var.get())
            self._on_change(self._pixel, new_wl)
        except ValueError:
            pass

if __name__ == "__main__":
    from tobes_ui.strong_lines import STRONG_LINES

    def test_cb(pixel, new_wavelength):
        """Callback function to handle the edited wavelength."""
        print(f"pixel: {pixel}, wavelength: {new_wavelength:.4f}")

    def main():
        """Main function to test the popup."""
        root = tk.Tk()
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.bind('<Escape>', lambda event: root.destroy())

        root.geometry("400x300")
        ttk.Label(root, text="This is the main window with some dummy content.").pack(pady=10)

        pixel = 10
        current_wl = 640.1234
        new_wl = 640.1235
        ref_lines = STRONG_LINES['Ne'].for_wavelength_range(range(638,660))

        ttk.Button(root,
                   text="Open Edit Wavelength Dialog",
                   command=lambda: WavelengthEditor(root, pixel, current_wl, new_wl,
                                                    ref_lines, test_cb)).pack(pady=10)

        ttk.Button(root, text="Quit", command=root.destroy).pack(pady=10)

        root.mainloop()

    main()
