#!/usr/bin/env python3
"""Calibration for Ocean Optics spectrometer"""

from enum import Enum
import queue
import pprint
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox


import numpy as np
import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from tobes_ui.calibration.common import ToolTip
from tobes_ui.calibration.strong_lines_control import StrongLinesControl
from tobes_ui.calibration.integration_control import IntegrationControl
from tobes_ui.calibration.sampling_control import SamplingControl
from tobes_ui.calibration.peak_detection_control import PeakDetectionControl
from tobes_ui.calibration.reference_match_control import ReferenceMatchControl
from tobes_ui.calibration.x_axis_control import XAxisControl
from tobes_ui.common import AttrDict
from tobes_ui.logger import LogLevel, configure_logging, LOGGER
from tobes_ui.spectrometer import ExposureMode, Spectrometer


class CaptureState(Enum):
    """State machine of the spectrum capture"""
    PAUSE = 0
    RUN = 1
    EXIT = 2


class CalibrationGUI: # pylint: disable=too-few-public-methods
    """GUI for Ocean spectrometer wavelength calibration."""

    def __init__(self, root, spectrometer, initial_polyfit):
        self._root = root
        self._root.title("Wavelength Calibration")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        #self._root.geometry("1024x768")
        #self._root.minsize(800, 600)

        self._spectrometer = spectrometer
        self._capture_state = CaptureState.PAUSE
        self._event_queue = queue.Queue()  # TK events submitted from non-main thread
        self._worker_thread = threading.Thread(target=self._data_refresh_loop, daemon=True)
        self._worker_thread.start()

        self._initial_polyfit = np.array(initial_polyfit)

        self._ui_elements = AttrDict()  # all the different UI elements we need access to

        # FIXME: rest of the data

        self._setup_ui()

        # debug info
        w = self._root.winfo_reqwidth()
        h = self._root.winfo_reqheight()
        print(f'window: {w}x{h}')
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        print(f"Primary display size: {screen_width}x{screen_height}")

        self._root.after(0, self._process_event_queue)

        self._update_status('Ready.')

    def _process_event_queue(self):
        while not self._event_queue.empty():
            event = self._event_queue.get_nowait()
            event()
        self._root.after(100, self._process_event_queue)

    def _push_event(self, event):
        if callable(event):
            self._event_queue.put(event)
        else:
            raise ValueError(f"Event {event} is not callable")

    def _setup_ui(self):
        paned_window = tk.PanedWindow(self._root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        paned_window.pack(fill=tk.BOTH, expand=True)

        left_frame = self._setup_left_frame(paned_window)
        right_frame = self._setup_right_frame(paned_window)

        paned_window.add(left_frame)
        paned_window.add(right_frame)

        # resize left to min(left minwidth, 30%)
        def _pw_on_resize(_event):
            total_width = paned_window.winfo_width()
            paned_window.paneconfig(left_frame, minsize=left_frame.winfo_reqwidth())
            paned_window.paneconfig(right_frame, minsize=right_frame.winfo_reqwidth())
            paned_window.sash_place(0, min(left_frame.winfo_reqwidth(), int(total_width * 0.3)), 0)
            # FIXME: ^^ probably doesn't work as I would expect...
        paned_window.bind('<Configure>', _pw_on_resize)

    def _setup_left_frame(self, parent):
        left_frame = ttk.Frame(parent)

        table_frame = ttk.Frame(left_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        poly_label = ttk.Label(table_frame, text="Pixels")
        poly_label.pack()

        # Create treeview for table
        columns = ('pixel', 'wl', 'new_wl')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=4)

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
            ('X⁰', f"{self._initial_polyfit[3]:e}"),
            ('X¹', f"{self._initial_polyfit[2]:e}"),
            ('X²', f"{self._initial_polyfit[1]:e}"),
            ('X³', f"{self._initial_polyfit[0]:e}"),
            ('R²', "-"),
            ('Serr', "-")
        ]
        for param, initial_val in parameters:
            poly_tree.insert('', 'end', values=(param, initial_val, '-'))

        # Controls
        controls_frame = ttk.Frame(left_frame)
        controls_frame.pack(fill=tk.X, padx=5, pady=5)
        self._ui_elements.capture_button = ttk.Button(controls_frame, text="Capture",
                                                      command=self._capture_action)
        self._ui_elements.capture_button.pack(side=tk.LEFT, padx=5)
        ToolTip(self._ui_elements.capture_button, 'Capture/freeze spectrum from the spectrometer.')

        self._ui_elements.save_button = ttk.Button(controls_frame, text="Save Cali",
                                                   command=lambda: print('save'), state='disabled')
        # FIXME: action ^^
        self._ui_elements.save_button.pack(side=tk.LEFT, padx=5)
        ToolTip(self._ui_elements.save_button, 'Save the wavelength calibration.')

        self._ui_elements.quit_button = ttk.Button(controls_frame, text="Quit",
                                                   command=self._quit_action)
        self._ui_elements.quit_button.pack(side=tk.RIGHT, padx=5)
        ToolTip(self._ui_elements.quit_button, 'Stop capture and quit the app.')

        # Strong lines
        slc = StrongLinesControl(left_frame)
        slc.on_change = lambda sl: pprint.pprint(
                {k: len([[vv.wavelength, vv.raw_flags] for vv in v]) for k,v in sl.items()})
        # FIXME: something more useful?
        slc.pack(fill="x", padx=5)

        status_frame = ttk.LabelFrame(left_frame, height=90, text='Status')
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        status_frame.pack_propagate(False)

        self._ui_elements.status_label = ttk.Label(status_frame, text="", justify=tk.LEFT,
                                                   anchor='nw')
        self._ui_elements.status_label.pack(fill=tk.BOTH, expand=True, padx=5)
        self._update_status('Initializing...')
        ToolTip(self._ui_elements.status_label,
                text=lambda: 'Status:\n' + self._ui_elements.status_label.cget('text'), above=True)

        return left_frame

    def _quit_action(self):
        """Quit button action handler"""
        # FIXME: only ask for confirmation once it's all working
        if True or messagebox.askokcancel("Quit", "Are you sure you want to quit?"): # pylint: disable=condition-evals-to-constant,line-too-long
            LOGGER.debug("Quitting...")
            self._update_status('Quitting...')
            self._on_close()

    def _capture_action(self):
        """Capture button action handler"""
        match self._capture_state:
            case CaptureState.RUN:
                # Stop capture
                LOGGER.debug("Stopping capture...")
                self._update_status('Stopping capture...')
                self._capture_state = CaptureState.PAUSE
                self._ui_elements.capture_button.config(text="Capture")

            case CaptureState.PAUSE:
                # Start capture
                LOGGER.debug("Starting capture...")
                self._update_status('Starting capture...')
                self._capture_state = CaptureState.RUN
                self._ui_elements.capture_button.config(text="Freeze")

            case _:
                # Ignore
                LOGGER.debug("unhandled state: %s", self._capture_state)
                self._update_status(f'Capture error: {self._capture_state}')

    def _process_spectrum(self, spectrum):
        """Processes captured spectrum"""
        if 'integration_control' in self._ui_elements:
            self._ui_elements.integration_control.integration_time = spectrum.time
        # FIXME: update self._ui_elements.plot (graph) here

    def _data_refresh_loop(self):
        # WARNING: Does NOT run in main thread; do not run any Tkinter code here!
        while True:
            match self._capture_state:
                case CaptureState.EXIT:
                    return

                case CaptureState.PAUSE:
                    time.sleep(0.1)

                case CaptureState.RUN:
                    def handle_spectrum(value):
                        LOGGER.debug("Got spectrum data with %s status and %.2f integration",
                                     value.status, value.time)
                        self._push_event(lambda: self._process_spectrum(value))
                        if self._capture_state != CaptureState.RUN:
                            self._push_event(lambda: self._update_status('Capture stopped.'))
                        return self._capture_state == CaptureState.RUN
                    self._push_event(lambda: self._update_status('Capture running...'))
                    self._spectrometer.stream_data(handle_spectrum)

    def _apply_integration_ctrl(self, data):
        """Applies integration control data to spectrometer"""
        LOGGER.debug(data)
        match data['mode']:
            case 'auto':
                self._spectrometer.properties_set_many({
                    'auto_min_exposure_time': data['min'] * 1000, # input in ms, set in µs
                    'auto_max_exposure_time': data['max'] * 1000, # input in ms, set in µs
                    'exposure_mode': ExposureMode.AUTOMATIC,
                })
            case 'manual':
                self._spectrometer.properties_set_many({
                    'exposure_time': data['value'] * 1000, # input in ms, set in µs
                    'exposure_mode': ExposureMode.MANUAL,
                })

    def _setup_right_frame(self, parent):
        right_frame = ttk.Frame(parent)

        controls_frame = ttk.Frame(right_frame)
        controls_frame.pack(fill=tk.X, padx=5, pady=5)

        controls = {
            'integration_control': IntegrationControl(controls_frame,
                                                      on_change=self._apply_integration_ctrl),
            'sampling_control': SamplingControl(controls_frame),
            'reference_match_control': ReferenceMatchControl(controls_frame),
            'peak_detection_control': PeakDetectionControl(controls_frame),
            'x_axis_control': XAxisControl(controls_frame),
        }

        col = 0
        for _name, control in controls.items():
            control.grid(column=col, row=0, sticky="news", padx=5, pady=5)
            control.columnconfigure(col, weight=1)
            col += 1

        self._ui_elements.update(controls)

        def _cf_on_resize(event):
            row = 0
            col = 0

            width = 0

            # FIXME: issue with this is that when you start new row, the width can stretch
            # (because when the cell on the next row is wider, it ends up stretching the
            # cell in all rows -- preceding and following)

            for _name, control in controls.items():
                if width + control.winfo_reqwidth() + 10 > event.width:
                    row += 1
                    col = 0
                    width = 0
                control.grid(column=col, row=row, sticky="news", padx=5, pady=5)
                control.columnconfigure(col, weight=1)
                col += 1
                width += control.winfo_reqwidth() + 10

        controls_frame.bind('<Configure>', _cf_on_resize)

        self._ui_elements.plot = self._setup_plot(right_frame)
        self._ui_elements.plot.pack(fill="both", expand=True)

        return right_frame

    def _setup_plot(self, parent):
        fig = Figure(figsize=(8,6), dpi=100) # FIXME: orly?
        axis = fig.add_subplot(111)

        axis.plot([], [], 'b-', linewidth=1)
        axis.set_xlabel('Wavelength (nm)')
        axis.set_ylabel('Counts')
        axis.set_title('Spectral Data')
        axis.grid(True, alpha=0.3)

        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()

        return canvas.get_tk_widget()

    def _update_status(self, message):
        if 'status_label' in self._ui_elements:
            self._ui_elements.status_label.config(text=message)
        else:
            print('Status:', message)

    def _on_close(self):
        self._update_status('Terminating capture...')
        self._capture_state = CaptureState.EXIT
        if self._worker_thread:
            self._worker_thread.join()
            self._worker_thread = None

        self._update_status('Terminating spectrometer...')
        if self._spectrometer:
            self._spectrometer.cleanup()
            self._spectrometer = None

        self._update_status('Bye!')
        self._root.destroy()

if __name__ == "__main__":
    def main():
        """Zee main(), like in C"""
        matplotlib.use('TkAgg')

        configure_logging(LogLevel.DEBUG) # FIXME: configurable?

        try:
            spectrometer = Spectrometer.create("oo:") # FIXME: maybe configurable?
        except Exception as ex: # pylint: disable=broad-exception-caught
            print("No spectrometer available", ex)
            sys.exit(1)

        if not spectrometer.supports_wavelength_calibration():
            print("Spectrometer doesn't support WL calibration.")
            sys.exit(2)

        wlc = spectrometer.read_wavelength_calibration()
        print("Read initial wavelength calibration coefficients:", wlc)

        root = tk.Tk()
        CalibrationGUI(root, spectrometer, initial_polyfit=wlc)
        root.mainloop()

    main()
