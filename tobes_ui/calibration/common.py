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


class ClampedSpinbox(ttk.Frame):  # pylint: disable=too-many-ancestors
    """Spinbox that holds an integer clamped to min_val, max_val range (inclusive)."""

    def __init__(self, parent, min_val=0, max_val=10, initial=None, label_text="", on_change=None,
                 **kwargs):  # pylint: disable=too-many-arguments
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
