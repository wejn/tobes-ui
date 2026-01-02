"""Common UI elements for the calibration."""

# pylint: disable=invalid-name

import abc

import tkinter as tk
from tkinter import ttk

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
        self.widget.bind("<ButtonPress>", self.hide_tooltip)
        self.widget.bind("<Destroy>", self.hide_tooltip)
        self.widget.bind("<Motion>", self.move)  # update position if mouse moves

    def schedule(self, _event=None):
        """Schedule showing the tooltip after a delay."""
        if self.after_id is None:
            self.after_id = self.widget.after(self.delay, self.show_tooltip)

    def show_tooltip(self):
        """Actually create and display the tooltip."""
        if self.tooltip is not None or self.after_id is None:
            return
        self.after_id = None

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
        label.grid(row=0, column=0)

        # Adjust position if it goes off the screen

        self.tooltip.update_idletasks()

        screen_width = self.tooltip.winfo_screenwidth()
        screen_height = self.tooltip.winfo_screenheight()
        tooltip_width = self.tooltip.winfo_width()
        tooltip_height = self.tooltip.winfo_height()

        if x + tooltip_width > screen_width:
            x = max(0, screen_width - tooltip_width)
        if y + tooltip_height > screen_height:
            y = max(0, screen_height - tooltip_height)

        self.tooltip.wm_geometry(f"+{x}+{y}")


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
        if self.tooltip is None:
            if self.after_id is not None:
                self.widget.after_cancel(self.after_id)
                self.after_id = None
            self.schedule()


class ClampedSpinbox(ttk.Frame):  # pylint: disable=too-many-ancestors
    """Spinbox that holds a number clamped to min_val, max_val range (inclusive)."""

    def __init__(self, parent, min_val=0, max_val=10, initial=None, label_text="", on_change=None,
                 allow_float=False, increment=1, **kwargs):  # pylint: disable=too-many-arguments
        super().__init__(parent, **kwargs)

        self._min_val = min_val
        self._max_val = max_val
        self._on_change = on_change
        self._allow_float = allow_float
        self._value_var = tk.StringVar(value=str(initial if initial is not None else self.min_val))
        self._last_valid = self._value_var.get()
        self._last_emitted = None
        self._disabled = False

        ttk.Label(self, text=label_text).grid(row=0, column=0, sticky="w")

        self._spinbox = ttk.Spinbox(
            self,
            from_=self.min_val,
            to=self.max_val,
            textvariable=self._value_var,
            validate="key",
            validatecommand=(self.register(self._validate), "%P"),
            width=max(len(str(self.min_val)), len(str(self.max_val))),
            command=self._apply_value,
            increment=increment
        )
        self._spinbox.grid(row=0, column=1, sticky="e", padx=(5, 0))

        self._spinbox.bind("<FocusOut>", lambda e: self._apply_value())
        self._spinbox.bind("<Return>", lambda e: self._apply_value(lose_focus=True))

        self.grid_columnconfigure(0, weight=1)

    @property
    def min_val(self):
        """Minimal value of the spinbox."""
        return self._min_val() if callable(self._min_val) else self._min_val

    @min_val.setter
    def min_val(self, val):
        self._min_val = val

    @property
    def max_val(self):
        """Maximal value of the spinbox."""
        return self._max_val() if callable(self._max_val) else self._max_val

    @max_val.setter
    def max_val(self, val):
        self._max_val = val

    @property
    def disabled(self):
        """Is the spinbox disabled?"""
        return self._disabled

    @disabled.setter
    def disabled(self, val):
        if val:
            self._spinbox.config(state="disabled")
            self._disabled = True
        else:
            self._spinbox.config(state="normal")
            self._disabled = False

    @property
    def on_change(self):
        "Getter for on_change."""
        return self._on_change

    @on_change.setter
    def on_change(self, proc):
        "Setter for on_change."""
        self._on_change = proc

    def _validate(self, new_value):
        """Per-keystroke validation - allow any numeric input."""
        if new_value in ("", "-"):
            return True
        if self._allow_float:
            try:
                float(new_value)
                return True
            except ValueError:
                return False
        else:
            return new_value.lstrip("-").isdigit()

    def _apply_value(self, lose_focus=False):
        """Apply and clamp value, trigger on_change."""
        if lose_focus:
            self.focus()
        self._spinbox.config(from_=self.min_val, to=self.max_val)

        try:
            if self._allow_float:
                value = float(self._value_var.get())
            else:
                value = int(self._value_var.get())
            value = max(self.min_val, min(self.max_val, value))
            value_str = str(value)
        except (ValueError, TypeError):
            value_str = self._last_valid
            if value_str is None or value_str == '':
                value_str = '0'
            value = float(value_str) if self._allow_float else int(value_str)

        self._value_var.set(value_str)
        self._last_valid = value_str
        self._spinbox.selection_clear()
        self._spinbox.icursor(tk.END)

        self._change_cb()

    def _change_cb(self, *args):
        """Change callback, to be executed when spinbox changes."""
        if self._on_change:
            value = self.get()
            if self._last_emitted is None or self._last_emitted != value:
                self._last_emitted = value
                self._on_change(value)

    def get(self):
        """Return current numeric value."""
        try:
            if self._allow_float:
                return float(self._value_var.get())
            return int(self._value_var.get())
        except ValueError:
            return float(self.min_val) if self._allow_float else self.min_val

    def set(self, value):
        """Set value programmatically (clamped)."""
        self._spinbox.config(from_=self.min_val, to=self.max_val)
        value = float(value) if self._allow_float else int(value)
        value = max(self.min_val, min(self.max_val, value))
        value_str = str(value)
        self._value_var.set(value_str)
        self._last_valid = value_str
        self._change_cb()

    def spinbox(self):
        """Get the underlying spinbox. Used (mainly?) for focus."""
        return self._spinbox


class CalibrationControlPanel(ttk.LabelFrame, abc.ABC):  # pylint: disable=too-many-ancestors
    """Control panel template."""

    def __init__(self, parent, text=None, on_change=None, **kwargs):
        super().__init__(parent, text=text or f'{self.__class__.__name__}', pad=5, **kwargs)

        self.on_change = on_change
        self._data = {}
        self._setup_gui()

    @abc.abstractmethod
    def _setup_gui(self):
        """Setup GUI elements for the control."""

    @property
    def on_change(self):
        """Get on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, proc):
        """Set on_change callback."""
        self._on_change = proc

    @property
    def controls_state(self):
        """Getter for the state that on_change emits."""
        return self._data

def float_to_string(num, max_len=14):
    """Format float num to string of up to max_len chars, with max precision possible.

    The max_len should be at least 8.
    """
    if max_len < 8:
        raise ValueError(f"max_len should be at least 8, is {max_len}")

    for precision in range(max_len, 0, -1):
        out = f"{num:.{precision}g}"
        if len(out) <= max_len:
            return out

    # Fallback that works (but might be less precise)
    return f"{num:.{max_len-7}e}" if num < 0 else f"{num:.{max_len-6}e}"
