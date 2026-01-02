#!/usr/bin/env python3
"""Calibration for Ocean Optics spectrometer"""

from enum import Enum
import queue
import pprint # pylint: disable=unused-import
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox


import numpy as np
import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
from scipy.signal import find_peaks

from tobes_ui.calibration.common import ToolTip
from tobes_ui.calibration.strong_lines_control import StrongLinesControl
from tobes_ui.calibration.integration_control import IntegrationControl
from tobes_ui.calibration.sampling_control import SamplingControl
from tobes_ui.calibration.peak_detection_control import PeakDetectionControl
from tobes_ui.calibration.reference_match_control import ReferenceMatchControl
from tobes_ui.calibration.wavelength_editor import WavelengthEditor
from tobes_ui.calibration.wavelength_save_dialog import WavelengthCalibrationSaveDialog
from tobes_ui.calibration.x_axis_control import XAxisControl
from tobes_ui.calibration.x_axis_zoom_control import XAxisZoomControl
from tobes_ui.common import AttrDict, SlidingMax, SpectrumAggregator
from tobes_ui.logger import LogLevel, configure_logging, LOGGER, set_level
from tobes_ui.spectrometer import ExposureMode, Spectrometer
from tobes_ui.strong_lines_container import StrongLinesContainer


class CaptureState(Enum):
    """State machine of the spectrum capture"""
    PAUSE = 0
    RUN = 1
    EXIT = 2


class WavelengthCalibrationGUI: # pylint: disable=too-few-public-methods
    """GUI for Ocean spectrometer wavelength calibration."""

    def __init__(self, root, spectrometer):
        if not spectrometer.supports_wavelength_calibration():
            raise ValueError("Spectrometer doesn't support WL calibration.")

        self._root = root
        self._root.title("Wavelength Calibration")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.geometry("1200x800")
        self._root.minsize(1200, 800)

        self._spectrometer = spectrometer
        self._capture_state = CaptureState.PAUSE
        self._event_queue = queue.Queue()  # TK events submitted from non-main thread
        self._worker_thread = threading.Thread(target=self._data_refresh_loop, daemon=True)
        self._worker_thread.start()

        initial_polyfit = self._spectrometer.read_wavelength_calibration()
        self._initial_polyfit = np.array(initial_polyfit)  # Current pixel -> wavelength polynomial
        self._new_polyfit = None  # New (calibrated) pixel -> wavelength polynomial
        self._new_polyfit_stats = None  # New polyfit stats
        self._x_axis_type = None  # Type of x axis coords (initial, fixed, new)
        self._x_axis_idx = None  # polyfit for the x axis (index for each pixel)

        self._ui_elements = AttrDict()  # all the different UI elements we need access to

        self._spectrum_agg = SpectrumAggregator(1)
        self._spectrum = None  # Spectrum captured by spectrometer (last)
        self._y_axis_max = SlidingMax(5)
        self._strong_lines = StrongLinesContainer({})
        self._peak_detector = None  # callable to detect peaks in spectrum data
        self._peaks = []  # list of peaks detected, indexed against spd_raw, not phys pixels
        self._calibration_points = {} # dict of pixels with new wl assigned to them

        self._x_axis_limits = None  # current x axis limits (min, max)
        self._ref_match_delta = [3, 3]  # reference match delta (minus_nm, plus_nm)

        self._annot_lims = None  # (xlim, ylim) for which annot was set up

        self._setup_ui()

        # Kick off event Q processing...
        self._root.after(0, self._process_event_queue)

        self._update_status('Ready.')

    def _process_event_queue(self):
        while not self._event_queue.empty():
            event = self._event_queue.get_nowait()
            event()
        if self._capture_state == CaptureState.RUN:
            # Make queue processing more snappy when capturing...
            self._root.after(20, self._process_event_queue)
        else:
            self._root.after(100, self._process_event_queue)

    def _push_event(self, event):
        if callable(event):
            self._event_queue.put(event)
        else:
            raise ValueError(f"Event {event} is not callable")

    def _setup_ui(self):
        self._root.grid_rowconfigure(0, weight=1)
        self._root.grid_columnconfigure(0, weight=1)

        # tweak rowheight of Treeviews
        font = tk.font.nametofont('TkDefaultFont')
        metrics = font.metrics()
        if 'linespace' in metrics:
            style = ttk.Style(self._root)
            style.configure('Treeview', font=font, rowheight=int(metrics['linespace']))

        paned_window = tk.PanedWindow(self._root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        paned_window.grid(row=0, column=0, sticky='nsew')

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
            # TODO: ^^ probably doesn't work as I would expect...
        paned_window.bind('<Configure>', _pw_on_resize)

    def _setup_calibration_points_table(self, parent):
        """Sets up the entire "Calibration Points" table (Treeview)."""
        table_frame = ttk.Frame(parent)
        table_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(1, weight=1)

        poly_label = ttk.Label(table_frame, text="Calibration Points")
        poly_label.grid(row=0, column=0, columnspan=2, sticky="n")

        # Create treeview for table
        columns = ('pixel', 'wl', 'new_wl')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=4)

        # Define headings
        tree.heading('pixel', text='pixel')
        tree.heading('wl', text='wl')
        tree.heading('new_wl', text='new_wl')

        # Configure column widths
        tree.column('pixel', width=50, anchor='e')
        tree.column('wl', width=85, anchor='e')
        tree.column('new_wl', width=85, anchor='e')

        # Scrollbar for table
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        def _on_delete(_event):
            """Handler for deleting points from the table."""
            if not tree.selection():
                return

            for item_id in tree.selection():
                pixel, _wl, _new_wl = tree.item(item_id, 'values')
                self._calibration_points.pop(int(pixel), None)

            self._update_calibration_points_table()
            self._update_plot(peaks=True)
            self._update_polyfit_table_and_ui_state()

        def _on_double_click(event):
            """Handler for editing points from the table (or adding arbitrary new ones)."""
            row_id = tree.identify_row(event.y)
            if row_id:
                pixel, _wl, _new_wl = tree.item(row_id, 'values')
                self._add_or_edit_pixel_dialog(int(pixel))
            else:
                self._add_or_edit_pixel_dialog(None)

        tree.bind('<Double-1>', _on_double_click)
        tree.bind('<Delete>', _on_delete)
        tree.bind('<KeyPress-Delete>', _on_delete)

        return tree

    def _setup_polyfit_table(self, parent):
        """Sets up the entire "Polynomial Fit" table (Treeview)"""
        # Polynomial fit
        poly_frame = ttk.Frame(parent, height=200)
        poly_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        poly_frame.grid_columnconfigure(0, weight=1)
        poly_frame.grid_rowconfigure(1, weight=1)

        poly_label = ttk.Label(poly_frame, text="Polynomial Fit")
        poly_label.grid(row=0, column=0, sticky="n")

        poly_table_frame = ttk.Frame(poly_frame)
        poly_table_frame.grid(row=1, column=0, sticky="nsew")
        poly_table_frame.grid_columnconfigure(0, weight=1)
        poly_table_frame.grid_rowconfigure(0, weight=1)

        poly_columns = ('parameter', 'initial', 'current')
        poly_tree = ttk.Treeview(poly_table_frame, columns=poly_columns, show='headings', height=6)

        poly_tree.heading('parameter', text='Param')
        poly_tree.heading('initial', text='Initial')
        poly_tree.heading('current', text='Current')

        poly_tree.column('parameter', width=30, anchor='w')
        poly_tree.column('initial', width=80, anchor='e')
        poly_tree.column('current', width=80, anchor='e')

        poly_tree.grid(row=0, column=0, sticky="nsew")

        parameters = [
            ('X⁰', f"{self._initial_polyfit[3]:e}"),
            ('X¹', f"{self._initial_polyfit[2]:e}"),
            ('X²', f"{self._initial_polyfit[1]:e}"),
            ('X³', f"{self._initial_polyfit[0]:e}"),
            ('R²',   "    n/a    "),
            ('Serr', "    n/a    ")
        ]
        for param, initial_val in parameters:
            poly_tree.insert('', 'end', values=(param, initial_val, '-'))

        return poly_tree

    def _setup_left_frame(self, parent):
        left_frame = ttk.Frame(parent)
        left_frame.grid_columnconfigure(0, weight=1)
        left_frame.grid_rowconfigure(0, weight=1)

        self._ui_elements.calibration_points_table = self._setup_calibration_points_table(
                left_frame)
        self._update_calibration_points_table()

        self._ui_elements.polyfit_table = self._setup_polyfit_table(left_frame)
        self._update_polyfit_table_and_ui_state()

        # Controls
        controls_frame = ttk.Frame(left_frame)
        controls_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        controls_frame.columnconfigure(0, weight=0)
        controls_frame.columnconfigure(1, weight=0)
        controls_frame.columnconfigure(2, weight=1)  # spacer
        controls_frame.columnconfigure(3, weight=0)

        self._ui_elements.capture_button = ttk.Button(controls_frame, text="Capture",
                                                      command=self._capture_action)
        self._ui_elements.capture_button.grid(row=0, column=0, padx=5)
        ToolTip(self._ui_elements.capture_button, 'Capture/freeze spectrum from the spectrometer.')

        self._ui_elements.save_button = ttk.Button(controls_frame, text="Save Cali",
                                                   command=self._save_calibration_action,
                                                   state='disabled',
                                                   )
        self._ui_elements.save_button.grid(row=0, column=1, padx=5)
        ToolTip(self._ui_elements.save_button, 'Save the wavelength calibration.')

        self._ui_elements.quit_button = ttk.Button(controls_frame, text="Quit",
                                                   command=self._quit_action)
        self._ui_elements.quit_button.grid(row=0, column=3, padx=5)
        ToolTip(self._ui_elements.quit_button, 'Stop capture and quit the app.')

        # Strong lines
        slc = StrongLinesControl(left_frame)
        slc.on_change = self._apply_strong_line_ctrl
        slc.grid(row=3, column=0, sticky="ew", padx=5)

        status_frame = ttk.LabelFrame(left_frame, height=90, text='Status')
        status_frame.grid(row=4, column=0, sticky="ew", padx=5, pady=5)
        status_frame.grid_propagate(False)

        self._ui_elements.status_label = ttk.Label(status_frame, text="", justify=tk.LEFT,
                                                   anchor='nw')
        self._ui_elements.status_label.grid(row=0, column=0, sticky="nsew", padx=5)
        self._update_status('Initializing...')
        ToolTip(self._ui_elements.status_label,
                text=lambda: 'Status:\n' + self._ui_elements.status_label.cget('text'), above=True)

        return left_frame

    def _execute_calibration_save(self, polyfit):
        """Executes calibration coeffs save to the eeprom, then updates UI."""

        if polyfit is None:
            LOGGER.error("No polyfit to save, yet save requested!")
            return

        self._spectrometer.write_wavelength_calibration(polyfit)
        self._update_status('Calibration saved.')

        self._initial_polyfit = polyfit
        self._update_polyfit_table_and_ui_state()
        self._update_calibration_points_table()
        self._apply_x_axis_ctrl({'mode': self._x_axis_type})

    def _save_calibration_action(self):
        """Triggers calibration save dialog."""

        cur_polyfit = self._initial_polyfit
        new_polyfit = self._new_polyfit

        if new_polyfit is None:
            LOGGER.error("No polyfit to save, yet save requested!")
            return

        def do_save():
            LOGGER.info("Current polyfit: %s", cur_polyfit)
            LOGGER.info("New polyfit: %s", new_polyfit)
            self._execute_calibration_save(new_polyfit)

        WavelengthCalibrationSaveDialog(
                parent=self._root,
                current_polyfit=cur_polyfit,
                new_polyfit=new_polyfit,
                on_change=do_save)

    def _recalculate_polyfit_data(self):
        """Recalculates polyfit data based on current calibration points."""
        if len(self._calibration_points) < 5:
            self._new_polyfit = None
            self._new_polyfit_stats = None
            return

        pixels = np.array(list(self._calibration_points.keys()))
        values = np.array(list(self._calibration_points.values()))

        degree = 3
        coeffs = np.polyfit(pixels, values, degree)

        poly = np.poly1d(coeffs)
        values_pred = poly(pixels)
        residuals = values - values_pred

        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((values - np.mean(values)) ** 2)
        r_squared = 1 - (ss_res / ss_tot)

        stderr = np.sqrt(ss_res / (len(values) - (degree + 1)))

        self._new_polyfit = coeffs
        self._new_polyfit_stats = [r_squared, stderr]

    def _update_polyfit_table_and_ui_state(self):
        """Updates polyfit table (and UI state) with current data."""
        self._recalculate_polyfit_data()

        tbl = self._ui_elements.polyfit_table
        row_to_id = tbl.get_children()

        if self._new_polyfit is None:
            if 'x_axis_control' in self._ui_elements:
                self._ui_elements.x_axis_control.new_enabled(False)
            if 'save_button' in self._ui_elements:
                self._ui_elements.save_button.config(state='disabled')
            for i in range(0, 6):
                tbl.set(row_to_id[i], column="current", value="-")
            return

        if 'x_axis_control' in self._ui_elements:
            self._ui_elements.x_axis_control.new_enabled(True)
        if 'save_button' in self._ui_elements:
            self._ui_elements.save_button.config(state='normal')
        # Poly
        for i in range(0, 4):
            tbl.set(row_to_id[i], column="initial", value=f"{self._initial_polyfit[3-i]:e}")
            tbl.set(row_to_id[i], column="current", value=f"{self._new_polyfit[3-i]:e}")
        # R^2
        tbl.set(row_to_id[4], column="current", value=f"{self._new_polyfit_stats[0]:e}")
        # Serr
        tbl.set(row_to_id[5], column="current", value=f"{self._new_polyfit_stats[1]:e}")

        if self._x_axis_type == 'new':
            self._apply_x_axis_ctrl({'mode': self._x_axis_type})

    def _update_calibration_points_table(self):
        """Updates calibration points table with current data."""
        tbl = self._ui_elements.calibration_points_table
        tbl.delete(*tbl.get_children())
        for pixel, new_wl in sorted(self._calibration_points.items()):
            cur_wl = np.polyval(self._initial_polyfit, pixel)
            tbl.insert('', 'end', values=(str(pixel), f'{cur_wl:.6f}', f'{new_wl:.6f}'))

    def _apply_strong_line_ctrl(self, data):
        LOGGER.debug("%s", {k: len(v) for k, v in data.items()})
        self._strong_lines = StrongLinesContainer(data)
        self._update_plot(references=True)
        num = len(self._strong_lines)
        if num > 500:
            self._update_status(f'Applied {num} references.\n(Super slow mode engaged.)')
        else:
            self._update_status(f'Applied {num} references.')

    def _quit_action(self):
        """Quit button action handler"""
        quitnow = len(self._calibration_points) < 2
        if quitnow or messagebox.askokcancel("Quit", "Are you sure you want to quit?"):
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
                self._clear_peaks()
                self._spectrum_agg.clear()
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
        spectrum.spd = {1: 1}  # Optimization to save some time, because we don't use `spd`
        self._spectrum = self._spectrum_agg.add(spectrum)
        self._update_plot(spectrum=True)

    PEAK_COLORS = AttrDict({
            'cali': '#89fe05',  # calibration point (lime green)
            'none': '#929591',  # no matches (grey)
            'single': '#fec615',  # unique match (golden yellow)
            'multi': '#d9544d',  # more than 1 match (pale red)
    })

    def _update_plot(self, spectrum=False, references=False, peaks=False):
        """Updates plot based on X-Axis config and data"""
        if 'plot_canvas' not in self._ui_elements:
            return

        canvas = self._ui_elements.plot_canvas
        fig = canvas.figure
        axis = fig.axes[0]

        xmargin = 5
        ymargin = 1.02

        if self._x_axis_idx is not None:
            idx = self._x_axis_idx
        else:
            idx = self._spectrum.wavelengths_raw

        if spectrum and self._spectrum:

            line = axis.get_lines()[0]

            spd = self._spectrum.spd_raw
            line.set_data(idx, spd)
            axis.set_ylabel(self._spectrum.y_axis)
            axis.set_title(f'Spectral Data ({self._spectrum.ts})')

            axis.set_ylim(bottom=0, top=self._y_axis_max.add(max(spd))*ymargin)

            # Set x axis limits (if need be)
            x_axis_limits = [self._x_axis_idx[0] - xmargin, self._x_axis_idx[-1] + 1 + xmargin]
            if self._x_axis_limits is None or self._x_axis_limits != x_axis_limits:
                axis.set_xlim(*x_axis_limits)
                if 'xaxis_zoom' in self._ui_elements:
                    self._ui_elements.xaxis_zoom.update_limits(xlim=x_axis_limits)
                self._x_axis_limits = x_axis_limits
                references = True  # redraw references on xlimit change

        if (self._spectrum
            and (((spectrum or references) and self._capture_state != CaptureState.RUN)
                 or peaks)):
            # Update peaks (because they depend on spectrum and refs)
            constants = self._spectrometer.constants()
            first_pixel = constants.first_pixel if 'first_pixel' in constants else 0

            def peak_color(pxl):
                """Colors for peaks, from https://xkcd.com/color/rgb/."""
                if pxl+first_pixel in self._calibration_points:
                    return self.PEAK_COLORS.cali

                refs = self._strong_lines.find_in_range(idx[pxl] - self._ref_match_delta[0],
                                                        idx[pxl] + self._ref_match_delta[1])
                match len(refs):
                    case 0:
                        return self.PEAK_COLORS.none
                    case 1:
                        return self.PEAK_COLORS.single
                    case _:
                        return self.PEAK_COLORS.multi

            peak_i = self._peaks
            peak_x = [idx[i] for i in peak_i]
            peak_y = [self._spectrum.spd_raw[i] for i in peak_i]
            peak_c = [peak_color(i) for i in peak_i]
            self._ui_elements.plot_peaks.set_offsets(np.c_[peak_x, peak_y])
            self._ui_elements.plot_peaks.set_facecolor(peak_c)

            if 'plot_legend' in self._ui_elements and len(self._peaks) > 1:
                self._ui_elements.plot_legend.set_visible(True)
            else:
                self._ui_elements.plot_legend.set_visible(False)

        if references:
            ax2 = fig.axes[1]

            # Remove old
            for line in ax2.lines:
                line.remove()

            # Add new, if needed
            ymax = 1000 * ymargin
            xlim = axis.get_xlim()

            if self._x_axis_limits is None:
                valid_x_range = [xlim[0] - xmargin, xlim[1] + xmargin + 1]
            else:
                valid_x_range = [self._x_axis_limits[0] - xmargin,
                                 self._x_axis_limits[1] + xmargin + 1]

            for x_coord, y_coord in zip(*self._strong_lines.plot_data(*valid_x_range)):
                ax2.axvline(x=x_coord, color='gray', ymax=y_coord/ymax, linewidth=1, zorder=0)
            axis.set_xlim(*xlim)

        canvas.draw_idle()

    def _clear_peaks(self):
        LOGGER.debug('go')
        self._peaks = []
        self._update_plot(peaks=True)

    def _detect_peaks(self):
        if self._spectrum is None:
            return

        if self._peak_detector is None:
            LOGGER.warning("bug: no peak detector")
            return

        self._peaks = list(self._peak_detector(self._spectrum.spd_raw))
        LOGGER.debug("Detected %d peaks", len(self._peaks))
        self._update_plot(peaks=True)

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
                        #LOGGER.debug("Got spectrum data with %s status and %.2f integration",
                        #             value.status, value.time)
                        self._push_event(lambda: self._process_spectrum(value))
                        if self._capture_state != CaptureState.RUN:
                            self._push_event(lambda: self._update_status('Capture stopped.'))
                            self._push_event(self._detect_peaks)
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

        self._spectrometer.property_set('max_fps', 0)  # TODO: maybe configurable?

    def _apply_peak_detect_ctrl(self, data):
        """Applies peak detection control data (configures peak finder)"""
        LOGGER.debug(data)

        def peak_detector(where):
            prom_percent = (data['prominence'] / 100) * np.max(where)
            peaks, _ = find_peaks(where, prominence=prom_percent, distance=data['distance'],
                                  wlen=data['window_length'])
            return peaks

        self._peak_detector = peak_detector

        if self._capture_state != CaptureState.RUN:
            self._detect_peaks()

    def _apply_refmatch_ctrl(self, data):
        """Applies reference match control data"""
        LOGGER.debug(data)
        self._ref_match_delta = [data['delta_minus'], data['delta_plus']]
        self._update_plot(peaks=True)

    def _setup_right_frame(self, parent):
        right_frame = ttk.Frame(parent)

        controls_frame = ttk.Frame(right_frame)
        controls_frame.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        if self._spectrometer.exposure_mode == ExposureMode.MANUAL:
            initial_ic = self._spectrometer.exposure_time / 1000
        else:
            initial_ic = None
        controls = {
            'integration_control': IntegrationControl(controls_frame, initial_ic=initial_ic,
                                                      on_change=self._apply_integration_ctrl),
            'sampling_control': SamplingControl(controls_frame,
                                                on_change=self._apply_sampling_ctrl),
            'reference_match_control': ReferenceMatchControl(controls_frame,
                                                             on_change=self._apply_refmatch_ctrl),
            'x_axis_control': XAxisControl(controls_frame, on_change=self._apply_x_axis_ctrl),
            'peak_detection_control': PeakDetectionControl(controls_frame,
                                                           on_change=self._apply_peak_detect_ctrl),
        }

        col = 0
        for _name, control in controls.items():
            control.grid(column=col, row=0, sticky="news", padx=5, pady=5)
            control.grid_columnconfigure(col, weight=1)
            col += 1

        self._ui_elements.update(controls)

        def _cf_on_resize(event):
            row = 0
            col = 0

            width = 0

            # TODO: issue with this is that when you start new row, the width can stretch
            # (because when the cell on the next row is wider, it ends up stretching the
            # cell in all rows -- preceding and following)

            for _name, control in controls.items():
                if width + control.winfo_reqwidth() + 10 > event.width:
                    row += 1
                    col = 0
                    width = 0
                control.grid(column=col, row=row, sticky="news", padx=5, pady=5)
                control.grid_columnconfigure(col, weight=1)
                col += 1
                width += control.winfo_reqwidth() + 10

        controls_frame.bind('<Configure>', _cf_on_resize)

        self._ui_elements.plot = self._setup_plot(right_frame)
        self._ui_elements.plot.grid(row=1, column=0, sticky='nsew')

        # When mouse over, set focus...
        self._ui_elements.plot.bind('<Enter>', lambda _event: self._ui_elements.plot.focus_set())

        canvas = self._ui_elements.plot_canvas
        axis = canvas.figure.axes[0]
        self._ui_elements.xaxis_zoom = XAxisZoomControl(right_frame, canvas, axis)
        self._ui_elements.xaxis_zoom.grid(row=2, column=0, sticky='nsew', padx=5, pady=5)

        right_frame.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=1)

        return right_frame

    def _apply_sampling_ctrl(self, data):
        """Applies Sampling Control data"""
        LOGGER.debug(data)
        self._spectrum_agg.func = data['mode'] or 'avg'
        self._spectrum_agg.window_size = data['samples'] or 1

    def _apply_x_axis_ctrl(self, data):
        """Applies X-Axis Control data"""
        LOGGER.debug(data)
        first_pixel = 0
        num_pixels = 1

        constants = self._spectrometer.constants()
        if 'first_pixel' in constants:
            first_pixel = constants['first_pixel']
        if 'num_pixels' in constants:
            num_pixels = constants['num_pixels']
        else:
            LOGGER.warning("Can't determine number of pixels, zeroing _x_axis_idx.")
            self._x_axis_idx = None
            self._x_axis_type = 'error'
            return

        pixels = np.array(range(first_pixel, num_pixels))
        match data['mode']:
            case 'init':
                self._x_axis_idx = np.polyval(self._initial_polyfit, pixels)
                self._x_axis_type = 'init'
            case 'fixed':
                self._x_axis_idx = np.linspace(data['min'], data['max'], num_pixels-first_pixel)

            case 'new':
                if self._new_polyfit is not None:
                    self._x_axis_idx = np.polyval(self._new_polyfit, pixels)
                    self._x_axis_type = 'new'
                else:
                    LOGGER.warning("_new_polyfit is None, using _initial_polyfit (and shouldn't)")
                    self._x_axis_idx = np.polyval(self._initial_polyfit, pixels)
                    self._x_axis_type = 'init'

            case _:
                LOGGER.warning("Unhandled x-axis mode %s, using pixels", data)
                self._x_axis_idx = pixels
                self._x_axis_type = 'pixels'

        self._update_plot(spectrum=True)

    def _add_or_edit_pixel_dialog(self, pixel, locked=True):
        """Triggers wavelength editor dialog for given pixel (already added or not)."""
        first_pixel = 0
        num_pixels = 1

        constants = self._spectrometer.constants()
        if 'first_pixel' in constants:
            first_pixel = constants['first_pixel']
        if 'num_pixels' in constants:
            num_pixels = constants['num_pixels']

        if locked and pixel is not None:
            valid_pixels = [pixel, pixel]
        else:
            valid_pixels = [first_pixel, num_pixels - 1]

        cur_wl = None
        if pixel:
            cur_wl = self._x_axis_idx[pixel - first_pixel]

        WavelengthEditor(parent=self._root,
                         pixel=pixel,
                         valid_pixels=valid_pixels,
                         pixel_to_wl=lambda pxl: self._x_axis_idx[pxl - first_pixel],
                         new_wl=self._calibration_points.get(pixel, cur_wl),
                         reference_lines_lookup=lambda cur_wl: self._strong_lines.find_in_range(
                             cur_wl - self._ref_match_delta[0],
                             cur_wl + self._ref_match_delta[1]),
                         on_change=self._add_calibration_point)

    def _add_calibration_point(self, pixel, wavelength):
        """Callback to add a pixel with given wavelength to calibration points."""
        LOGGER.debug("add pixel: %d: %f", pixel, wavelength)
        self._calibration_points[pixel] = wavelength
        self._update_calibration_points_table()
        self._update_plot(peaks=True)
        self._update_polyfit_table_and_ui_state()

    def _on_peak_pick(self, event):
        """Callback that gets called when a detected peaks gets picked."""
        if event.guiEvent.num in [1, 2, 3]:
            idx = event.ind[-1]
            if idx < len(self._peaks):
                constants = self._spectrometer.constants()
                first_pixel = constants.first_pixel if 'first_pixel' in constants else 0
                pixel = self._peaks[idx] + first_pixel
                if event.guiEvent.num == 1:
                    self._add_or_edit_pixel_dialog(pixel)
                elif event.guiEvent.num in [2, 3]:
                    if pixel in self._calibration_points:
                        self._calibration_points.pop(int(pixel), None)
                        self._update_calibration_points_table()
                        self._update_plot(peaks=True)
                        self._update_polyfit_table_and_ui_state()
            else:
                LOGGER.warning('peak %d not found (len(_peaks): %d)', idx, len(self._peaks))

    def _on_plot_scroll(self, event):
        """Callback on scroll events."""
        if self._ui_elements.xaxis_zoom is not None:
            if event.button == 'up':
                self._ui_elements.xaxis_zoom.zoom_in(center=event.xdata)
            elif event.button == 'down':
                self._ui_elements.xaxis_zoom.zoom_out(center=event.xdata)
        self._on_motion(event=None)

    def _setup_plot(self, parent):
        matplotlib.pyplot.rcParams.update({'figure.autolayout': True})

        fig = Figure()
        axis = fig.add_subplot(111)

        axis.plot([380, 780], [0, 0], 'b-', linewidth=1)
        axis.set_ylim(bottom=0, top=1000*1.02)
        axis.set_xlabel('Wavelength (nm)')
        axis.set_ylabel('Counts')
        axis.set_title('Spectral Data')
        axis.grid(True, alpha=0.3)
        axis.set_aspect('auto')

        self._ui_elements.plot_peaks = axis.scatter([], [], c='gray',
                                                    marker='o', label='Peaks', zorder=3,
                                                    picker=0)

        cali = mpatches.Patch(color=self.PEAK_COLORS.cali, label='Cali point')
        none = mpatches.Patch(color=self.PEAK_COLORS.none, label='No ref')
        single = mpatches.Patch(color=self.PEAK_COLORS.single, label='Single ref')
        multi = mpatches.Patch(color=self.PEAK_COLORS.multi, label='Multi refs')
        self._ui_elements.plot_legend = axis.legend(handles=[cali, none, single, multi])
        self._ui_elements.plot_legend.set_visible(False)

        ax2 = axis.twinx()
        ax2.set_visible(True)
        ax2.spines['right'].set_visible(True)
        ax2.tick_params(axis='y', which='both', length=0, labelleft=False, labelright=False)

        axis.set_zorder(ax2.get_zorder() + 1)
        axis.set_frame_on(False)

        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()

        fig.set_layout_engine('compressed')

        canvas.mpl_connect('pick_event', self._on_peak_pick)
        canvas.mpl_connect('scroll_event', self._on_plot_scroll)
        canvas.mpl_connect('motion_notify_event', self._on_motion)
        canvas.mpl_connect('key_press_event', self._on_keypress)

        self._ui_elements.pixel_annotation = axis.annotate(
                "",
                xy=(0,0),
                xytext=(15,15),
                textcoords='offset points',
                bbox={'boxstyle': 'round,pad=0.5', 'fc': '#cafffb', 'alpha': 0.9},
                arrowprops={'arrowstyle': '->', 'connectionstyle': 'arc3,rad=0'})
        self._ui_elements.pixel_annotation.set_visible(False)


        self._ui_elements.plot_canvas = canvas

        return canvas.get_tk_widget()

    def _on_keypress(self, event):
        """Handler for key press events from the canvas."""
        xdata = None
        if 'plot_canvas' in self._ui_elements and event.x is not None:
            canvas = self._ui_elements.plot_canvas
            fig = canvas.figure
            axis = fig.axes[0]
            if event.inaxes == axis:
                xdata = axis.transData.inverted().transform((event.x, 0))[0]
        match event.key:
            case '+':
                if 'xaxis_zoom' in self._ui_elements:
                    self._ui_elements.xaxis_zoom.zoom_in(xdata)
            case '-':
                if 'xaxis_zoom' in self._ui_elements:
                    self._ui_elements.xaxis_zoom.zoom_out(xdata)
            case 'right':
                if 'xaxis_zoom' in self._ui_elements:
                    self._ui_elements.xaxis_zoom.scroll_by(1)
            case 'left':
                if 'xaxis_zoom' in self._ui_elements:
                    self._ui_elements.xaxis_zoom.scroll_by(-1)
            case 'enter':  # Trigger point add based on current annotation...
                if 'pixel_annotation' in self._ui_elements:
                    annot = self._ui_elements.pixel_annotation
                    constants = self._spectrometer.constants()
                    first_pixel = constants.first_pixel if 'first_pixel' in constants else 0
                    nearest_idx, _nearest_x = self._nearest_peak(annot.xy[0])
                    if nearest_idx:
                        pixel = nearest_idx + first_pixel
                        self._add_or_edit_pixel_dialog(int(pixel))
            case _:
                #print(f"Unhandled key: {event.key}")
                pass

    def _nearest_peak(self, x):
        """Given X, return the nearest index in self._x_axis_idx and nearest value."""
        if self._spectrum is None or x is None or self._x_axis_idx is None:
            return [None, None]

        if self._peaks is None or not self._peaks:
            return [None, None]

        idx = self._x_axis_idx
        peak_x = np.array([idx[i] for i in self._peaks])
        distances = np.sqrt((peak_x - x)**2)

        nearest = self._peaks[np.argmin(distances)]
        return [nearest, idx[nearest]]

    def _on_motion(self, event):
        if self._capture_state != CaptureState.PAUSE or self._spectrum is None:
            return
        if 'pixel_annotation' not in self._ui_elements:
            return
        if 'plot_canvas' not in self._ui_elements:
            return

        annot = self._ui_elements.pixel_annotation
        canvas = self._ui_elements.plot_canvas
        fig = canvas.figure
        axis = fig.axes[0]

        if event:
            xdata = event.xdata
        elif annot.get_visible():
            xdata = annot.xy[0]
        else:
            xdata = None
        nearest_idx, nearest_x = self._nearest_peak(xdata)

        if nearest_idx is None:
            if annot.get_visible():
                annot.set_visible(False)
                canvas.draw_idle()
            return

        constants = self._spectrometer.constants()
        first_pixel = constants.first_pixel if 'first_pixel' in constants else 0
        pixel = nearest_idx + first_pixel

        redraw = False

        if not annot.get_visible():
            annot.set_visible(True)
            redraw = True

        if self._annot_lims is None or self._annot_lims != (axis.get_xlim(), axis.get_ylim()):
            redraw = True

        # Prep text
        text = f"Pixel: {pixel}\nCur WL: {nearest_x:.6f}"
        if pixel in self._calibration_points:
            text += f"\nSet WL: {self._calibration_points[pixel]:.6f}"
        if self._new_polyfit is not None:
            new_val = np.polyval(self._new_polyfit, pixel)
            text += f"\nNew WL: {new_val:.6f}"
        refs = self._strong_lines.find_in_range(nearest_x - self._ref_match_delta[0],
                                                nearest_x + self._ref_match_delta[1])
        if len(refs) > 0:
            text += f"\n{len(refs)} Refs:"
            for r in sorted(refs, key=lambda ref: abs(nearest_x - ref.wavelength))[:5]:
                text += f"\n  ({r.wavelength-nearest_x:+.2f}) {r}"
            if len(refs) > 5:
                text += "\n  (...)"

        if redraw or annot.get_text() != text:
            annot.set_text(text)
            redraw = True
            annot.set_visible(True)

        if redraw or annot.xy[0] != nearest_x:
            annot.set(position=(0, 0))

            nearest_y = self._spectrum.spd_raw[nearest_idx]
            annot.xy = (nearest_x, nearest_y)

            xlim = axis.get_xlim()
            ylim = axis.get_ylim()
            xrange = xlim[1] - xlim[0]
            yrange = ylim[1] - ylim[0]
            xnorm = (nearest_x - xlim[0]) / xrange if xrange != 0 else 0.5
            ynorm = (nearest_y - ylim[0]) / yrange if yrange != 0 else 0.5

            if hasattr(annot, '_arrow_relpos'):
                # XXX: I wish there were public api for this; there ain't
                annot._arrow_relpos = (xnorm, ynorm) # pylint: disable=protected-access

            offset_scale = 15
            bb = annot.get_window_extent()
            xx = - 2*offset_scale*xnorm + offset_scale - (bb.width / fig.dpi * 72)*xnorm
            yy = -offset_scale - bb.height / fig.dpi * 72 if ynorm > 0.67 else offset_scale

            annot.set(position=(xx, yy))
            self._annot_lims = (xlim, ylim)
            redraw = True

        if redraw:
            #LOGGER.debug('redraw: %s', nearest_x)
            canvas.draw_idle()

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

        configure_logging(LogLevel.DEBUG)
        set_level(LogLevel.INFO, 'oceanoptics')  # way less noisy, TY

        try:
            spectrometer = Spectrometer.create("oo:")
        except Exception as ex: # pylint: disable=broad-exception-caught
            print("No spectrometer available", ex)
            sys.exit(1)

        if not spectrometer.supports_wavelength_calibration():
            print("Spectrometer doesn't support WL calibration.")
            sys.exit(2)

        root = tk.Tk()
        WavelengthCalibrationGUI(root, spectrometer)
        root.mainloop()

    main()
