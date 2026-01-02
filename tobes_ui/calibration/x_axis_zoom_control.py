"""Zoom control for X axis of a matplotlib's plot."""

import tkinter as tk
from tkinter import ttk


class XAxisZoomControl(ttk.Frame):  # pylint: disable=too-many-ancestors
    """Zoom control for X axis of a matplotlib's plot."""

    def __init__(self, parent, canvas, ax, zoom_factor=1.5, **kwargs):
        super().__init__(parent, **kwargs)

        self._canvas = canvas
        self._ax = ax
        self._zoom_factor = zoom_factor

        self._full_xlim = self._ax.get_xlim()
        self._current_xlim = list(self._full_xlim)

        self._create_widgets()
        self._update_controls_state()

    def update_limits(self, xlim=None, reset_zoom=False, redraw=False):
        """Update limits of the graph. If xlim not given, it's taken from the ax."""
        if xlim is None:
            xlim = self._ax.get_xlim()

        if reset_zoom:
            self._full_xlim = xlim
            self._current_xlim = list(self._full_xlim)
        else:
            old_full_width = self._full_width
            zoom_level = self._current_width / old_full_width

            center = self._center
            if old_full_width > 0:
                center_ratio = (center - self._full_xlim[0]) / old_full_width
            else:
                center_ratio = 0.5

            self._full_xlim = xlim
            new_full_width = self._full_width

            new_width = new_full_width * zoom_level
            new_center = self._full_xlim[0] + center_ratio * new_full_width

            self._current_xlim[0] = new_center - new_width / 2
            self._current_xlim[1] = new_center + new_width / 2

        self._clamp_limits()
        self._update_controls_state()
        if redraw:
            self._update_plot()

    @property
    def _full_width(self):
        """Full width of the x-axis range."""
        return self._full_xlim[1] - self._full_xlim[0]

    @property
    def _current_width(self):
        """Current width of the visible x-axis range."""
        return self._current_xlim[1] - self._current_xlim[0]

    @property
    def _center(self):
        """Center point of current view."""
        return (self._current_xlim[0] + self._current_xlim[1]) / 2

    def _create_widgets(self):
        button_frame = ttk.Frame(self)
        button_frame.pack(side=tk.LEFT, padx=(0, 5))

        self._zoom_in_btn = ttk.Button(button_frame, text="+", width=3, command=self.zoom_in)
        self._zoom_in_btn.pack(side=tk.LEFT, padx=2)

        self._zoom_out_btn = ttk.Button(button_frame, text="-", width=3, command=self.zoom_out)
        self._zoom_out_btn.pack(side=tk.LEFT, padx=2)

        self._scrollbar = ttk.Scale(self, from_=0, to=0, orient=tk.HORIZONTAL,
                                    command=self._on_scroll)
        self._scrollbar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._scrollbar.set(0)

    def _apply_zoom(self, width_multiplier, center=None):
        """Apply zoom with given width multiplier, maintaining center point."""
        if center is None:
            center = self._center

        new_width = self._current_width * width_multiplier

        if self._current_width > 0:
            ratio = (center - self._current_xlim[0]) / self._current_width
        else:
            ratio = 0.5

        self._current_xlim[0] = center - new_width * ratio
        self._current_xlim[1] = center + new_width * (1 - ratio)

        self._clamp_limits()
        self._update_plot()
        self._update_controls_state()

    def zoom_in(self, center=None):
        """Zooms in (increase magnification)."""
        self._apply_zoom(1.0 / self._zoom_factor, center)

    def zoom_out(self, center=None):
        """Zooms out (decrease magnification)."""
        self._apply_zoom(self._zoom_factor, center)

    def scroll_by(self, delta):
        """Applies scroll delta"""
        self._scrollbar.set(self._scrollbar.get() + delta)

    def _on_scroll(self, value):
        value = float(value)
        current_width = self._current_width # must cache, changing _current_xlim!

        scroll_range = self._full_width - current_width
        if scroll_range > 0:
            offset = (value / 100) * scroll_range
            self._current_xlim[0] = self._full_xlim[0] + offset
            self._current_xlim[1] = self._current_xlim[0] + current_width

            self._clamp_limits()
            self._update_plot()

    def _clamp_limits(self):
        current_width = self._current_width # must cache, changing _current_xlim!

        if current_width > self._full_width:
            self._current_xlim = list(self._full_xlim)
            return

        if self._current_xlim[0] < self._full_xlim[0]:
            self._current_xlim[0] = self._full_xlim[0]
            self._current_xlim[1] = self._current_xlim[0] + current_width

        if self._current_xlim[1] > self._full_xlim[1]:
            self._current_xlim[1] = self._full_xlim[1]
            self._current_xlim[0] = self._current_xlim[1] - current_width

    def _update_plot(self):
        self._ax.set_xlim(self._current_xlim)
        self._canvas.draw_idle()

    def _update_scrollbar(self):
        full_width = self._full_width
        current_width = self._current_width

        if current_width >= full_width:
            self._scrollbar.configure(from_=0, to=0)
            self._scrollbar.set(0)
        else:
            self._scrollbar.configure(from_=0, to=100)
            offset = self._current_xlim[0] - self._full_xlim[0]
            scroll_range = full_width - current_width
            value = (offset / scroll_range) * 100 if scroll_range > 0 else 0
            self._scrollbar.set(value)

    def _update_controls_state(self):
        if self._current_width >= self._full_width * 0.999:
            self._zoom_out_btn.state(['disabled'])
        else:
            self._zoom_out_btn.state(['!disabled'])

        self._update_scrollbar()


if __name__ == "__main__":
    # pylint: disable=invalid-name
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.pyplot as plt
    import numpy as np

    def main():
        """C-style main()."""

        root = tk.Tk()
        root.title("X-Axis Zoom Control Demo")
        root.geometry("800x600")

        fig, ax = plt.subplots()
        x = np.linspace(0, 100, 1000)
        y = np.sin(x / 5) * np.exp(-x / 50)
        line, = ax.plot(x, y)
        ax.set_xlabel("X Axis")
        ax.set_ylabel("Y Axis")
        ax.set_title("Plot with X-Axis Zoom Control")
        ax.grid(True, alpha=0.3)
        ax.set_aspect('auto')

        canvas = FigureCanvasTkAgg(fig, master=root)
        canvas.draw()
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        zoom_control = XAxisZoomControl(root, canvas, ax)
        zoom_control.grid(row=1, column=0, sticky='ew', padx=5, pady=5)

        def on_scroll(event):
            if event.xdata is not None:
                if event.button == 'up':
                    zoom_control.zoom_in(center=event.xdata)
                elif event.button == 'down':
                    zoom_control.zoom_out(center=event.xdata)

        canvas.mpl_connect('scroll_event', on_scroll)

        def update_plot(reset_zoom=False):
            new_x = np.linspace(0, 200, 1000)
            new_y = np.sin(new_x / 5) * np.exp(-new_x / 50)
            line.set_data(new_x, new_y)
            ax.relim()
            ax.autoscale_view()
            zoom_control.update_limits(xlim=(0, 200), reset_zoom=reset_zoom, redraw=True)

        button_frame = tk.Frame(root)
        button_frame.grid(row=2, column=0, padx=10, pady=10)

        update_btn = ttk.Button(button_frame,
                                text="Update Plot (0-200)",
                                command=update_plot)
        update_btn.grid(row=0, column=0, padx=5, pady=5)

        update2_btn = ttk.Button(button_frame,
                                 text="Update Plot (0-200) + Reset zoom",
                                 command=lambda: update_plot(True))
        update2_btn.grid(row=0, column=1, padx=5, pady=5)

        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # There's some race, not sure what... this fixes it
        root.after(50, lambda: canvas_widget.grid_configure(padx=0, pady=0))

        root.mainloop()

    main()
