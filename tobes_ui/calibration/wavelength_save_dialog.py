"""Wavelength calibration save form (dialog)."""

import tkinter as tk
from tkinter import ttk
from tkinter.simpledialog import Dialog

import numpy as np

from tobes_ui.calibration.common import float_to_string


class WavelengthCalibrationSaveDialog(Dialog):
    """Popup dialog for saving new calibration polynomial."""

    def __init__(self, parent, current_polyfit, new_polyfit, on_change):
        self._current_polyfit = current_polyfit
        self._new_polyfit = new_polyfit
        self._on_change = on_change

        super().__init__(parent, title="Save Wavelength Calibration")

    def body(self, master):
        """Create and place widgets in the dialog body."""

        # Warning message
        warning = (
            "WARNING:\n"
            "Please BACK UP the calibration values below before pressing OK.\n"
            "Original values will be rewritten permanently (no built-in undo)."
        )
        warning_label = ttk.Label(
            master,
            text=warning,
            foreground="red",
            justify="left"
        )
        warning_label.grid(row=0, column=0, columnspan=2, sticky="we", pady=10)

        # Current calibration
        ttk.Label(master, text="Current calibration (back up):").grid(
            row=1, column=0, sticky="w"
        )
        self.current_text = self._create_text_box(master)
        self.current_text.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        self._fill_text(self.current_text, self._current_polyfit)

        # New calibration
        ttk.Label(master, text="New calibration:").grid(
            row=1, column=1, sticky="w"
        )
        self.new_text = self._create_text_box(master)
        self.new_text.grid(row=2, column=1, sticky="nsew")
        self._fill_text(self.new_text, self._new_polyfit)

        # Layout behavior
        master.grid_rowconfigure(2, weight=1)
        master.grid_columnconfigure(0, weight=1)
        master.grid_columnconfigure(1, weight=1)

        return None  # no initial focus

    def _create_text_box(self, master):
        text = tk.Text(master, height=4, width=20, wrap="none")
        text.configure(state="disabled")
        return text

    def _fill_text(self, widget, values):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", "\n".join([float_to_string(v) for v in values[::-1]]))
        widget.configure(state="disabled")

    def apply(self):
        """
        Called automatically when OK is pressed.
        """
        self._on_change()

if __name__ == "__main__":
    def main():
        """Main function to test the popup."""
        root = tk.Tk()
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.bind('<Escape>', lambda event: root.destroy())

        root.grid_columnconfigure(0, weight=1)

        root.geometry("400x300")
        ttk.Label(root, text="This is the main window with some dummy content.").grid(
                row=0, column=0, pady=10)

        old = np.array([-1.10723200e-09, -2.10060600e-05, 3.80489000e-01, 3.41206390e+02])
        new = np.array([-2.03692509e-09, -1.83460977e-05, 3.78184170e-01, 3.43182843e+02])

        def on_change():
            print("Save triggered.")

        ttk.Button(root,
                   text="Open Save Wavelength Cali Dialog",
                   command=lambda: WavelengthCalibrationSaveDialog(root, old, new, on_change),
                   ).grid(row=1, column=0, pady=10)

        ttk.Button(root, text="Quit", command=root.destroy).grid(row=2, column=0, pady=10)

        root.mainloop()

    main()
