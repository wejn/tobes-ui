"""Nice UI for TorchBearer Spectrometer"""

import argparse
import atexit
import os
import pprint
import queue
import signal
import sys
import threading
import time
import warnings

import colour
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.backend_tools import ToolBase, ToolToggleBase
from matplotlib.backend_tools import default_toolbar_tools

import protocol
import spectrometer

# pylint: disable=broad-exception-caught
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments

# Remove all tools by default (ouch)
default_toolbar_tools.clear()


class QuickGraphTool(ToolToggleBase):
    """Quick Graph toggle for the toolbar"""
    description = 'Quick vs. colorful graph (key: Q)'
    default_keymap = ['Q', 'q']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        self.default_toggled = self.plot.quick_graph
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/quick")
        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        self.plot.quick_graph = True
        self.plot.update_plot()

    def disable(self, event=None):
        self.plot.quick_graph = False
        self.plot.update_plot()


class PlotSaveTool(ToolBase):
    """Plot data save button for the toolbar"""
    description = 'Save plot data as png (key: S)'
    default_keymap = ['S', 's']

    def __init__(self, *args, plot, file_template, **kwargs):
        self.plot = plot
        self.file_template = file_template
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/plot_save")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        snap_time = self.plot.data.ts
        if not self.file_template:
            print("File template not defined, can't save")
        else:
            template_values = {
                    'timestamp': str(int(snap_time.timestamp())),
                    'timestamp_full': str(snap_time.timestamp()),
                    'timestamp_human': str(snap_time),
            }
            filename = self.file_template.format(**template_values) + '.png'
            self.plot.fig.savefig(filename, format='png')
            print('Plot saved as:', filename)


class RawSaveTool(ToolBase):
    """Raw data save button for the toolbar"""
    description = 'Save raw data as json (key: D)'
    default_keymap = ['D', 'd']

    def __init__(self, *args, plot, file_template, **kwargs):
        self.plot = plot
        self.file_template = file_template
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/raw_save")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        snap_time = self.plot.data.ts
        if not self.file_template:
            print(self.plot.data.to_json())
        else:
            template_values = {
                    'timestamp': str(int(snap_time.timestamp())),
                    'timestamp_full': str(snap_time.timestamp()),
                    'timestamp_human': str(snap_time),
            }
            filename = self.file_template.format(**template_values) + '.json'
            with open(filename, 'w', encoding='utf-8') as file:
                file.write(self.plot.data.to_json())
            print('Raw data saved as:', filename)


class OneShotTool(ToolBase):
    """One Shot button for the toolbar"""
    description = 'One good acquisition (key: 1 || O)'
    default_keymap = ['1', 'O', 'o']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/oneshot")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        print('Oneshot refresh...')
        self.plot.oneshot = True


class PowerTool(ToolBase):
    """Quit button for the toolbar"""
    description = 'Quit application (key: Esc)'
    default_keymap = ['escape', 'ctrl+q', 'ctrl+Q']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/power")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.stop()


class RefreshTool(ToolToggleBase):
    """Refresh data toggle for the toolbar"""
    description = 'Keep refreshing data (key: R)'
    default_keymap = ['r', 'R']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        self.default_toggled = self.plot.keep_refreshing
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/refresh")
        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        self.plot.keep_refreshing = True
        self.plot.update_status()

    def disable(self, event=None):
        self.plot.keep_refreshing = False
        self.plot.update_status()


class RefreshableSpectralPlot:
    """Refreshable plot (graph); basically main window of the app"""
    def __init__(self, initial_data, refresh_func=None, quick_graph=False,
                 oneshot=False, file_template=None):
        self.data = initial_data
        self.running = False
        self.thread = None
        self.fig = None
        self.axes = None
        self.update_queue = queue.Queue()
        self.cursor_dot = None
        self.cursor_dot2 = None
        self.cursor_text = None
        self.last_mouse_pos = None  # Store last mouse position
        self.cursor_visible = False  # Track cursor visibility state
        self.refresh_func = refresh_func
        self.keep_refreshing = not oneshot
        self.oneshot = oneshot
        self.data_status = 'initializing'
        self.quick_graph = quick_graph
        self.file_template = file_template

    WARNINGS_TO_IGNORE = [
            "Treat the new Tool classes introduced in v1.5 as experimental",
            "Key r changed from home to refresh",
            "Key q changed from quit to quick",
            "Key s changed from save to plot_save",
            "Key o changed from zoom to oneshot",
    ]

    def start_plot(self):
        """Start the plotting in main thread; blocks"""
        for warning in self.WARNINGS_TO_IGNORE:
            warnings.filterwarnings("ignore", warning)
        plt.rcParams['toolbar'] = 'toolmanager'
        spd = self.data.to_spectral_distribution()
        self.fig, self.axes = colour.plotting.plot_single_sd(spd, show=False,
                                                             transparent_background=False)
        plt.xlabel("Wavelength $\\lambda$ (nm)")
        plt.ylabel("Spectral Distribution ($W/m^2$)")
        plt.ylim([0, 0.1]) # initial
        self._setup_cursor()
        self.update_status()

        plt.ion()
        plt.show(block=False)
        self.fig.canvas.draw()

        self._add_toolbar_buttons()

        # Start background data generation
        self.running = True
        self.thread = threading.Thread(target=self._data_loop, daemon=True)
        self.thread.start()

        def trim_queue():
            queue_size = self.update_queue.qsize()
            if queue_size > 2:
                print(f"Warning: Queue size: {queue_size} (refresh too fast?); squashing")
                while self.update_queue.qsize() > 1:
                    self.update_queue.get_nowait()

        # Main thread handles GUI updates
        try:
            while self.running:
                # Check for new data
                try:
                    # The colour.plotting.plot_single_sd() is too slow (0.5s on my machine).
                    # So we need to manage the queue
                    trim_queue()
                    new_data = self.update_queue.get_nowait()
                    self.data = new_data
                    self.update_plot()
                except queue.Empty:
                    if not self.keep_refreshing and not self.oneshot:
                        self.data_status = 'idle'

                # Safely handle matplotlib events
                try:
                    plt.pause(0.01)
                except Exception as ex:
                    # Catch any matplotlib/Tkinter exceptions during shutdown
                    if self.running:  # Only print if we're not shutting down
                        print(f"Matplotlib error: {ex}")
                    break
        except (KeyboardInterrupt, SystemExit):
            self.stop()
        finally:
            self.stop()

    def _refresh_cb(self, data):
        """Refresh callback that receives new spectral data, returns if further refreshes wanted"""
        if self.keep_refreshing or self.oneshot:
            match data.status:
                case protocol.ExposureStatus.NORMAL:
                    self.update_queue.put(data)
                    self.data_status = 'ok'
                    if self.oneshot:
                        self.oneshot = False

                case protocol.ExposureStatus.UNDER:
                    self.data_status = 'under-exposed'

                case protocol.ExposureStatus.OVER:
                    self.data_status = 'over-exposed'

                case _:
                    self.data_status = 'error: ' + str(data.status)

        return self.running and (self.keep_refreshing or self.oneshot)

    def _data_loop(self):
        """Background thread that generates new data throuh refresh func"""
        while self.running:
            try:
                time.sleep(1)
                if not self.keep_refreshing and not self.oneshot:
                    continue

                if self.refresh_func:
                    self.refresh_func(self._refresh_cb)
                else:
                    print("No refresh func?!")
            except Exception:
                # If we can't get new data, just continue
                if self.running:
                    break

    def update_plot(self):
        """Update plot in main thread"""
        try:
            # Clear the existing axes instead of the whole figure
            self.axes.clear()
            # Plot directly to the existing axes
            #start = time.perf_counter()
            spd = self.data.to_spectral_distribution()
            plt.title(f"{spd.display_name}")
            if self.quick_graph:
                self.axes.plot(list(spd.wavelengths),
                             list(spd.values),
                             label='Spectral Distribution')
            else:
                colour.plotting.plot_single_sd(spd, axes=self.axes,
                                               show=False, transparent_background=False)

            #print(f"Elapsed time: {time.perf_counter() - start} seconds")
            plt.xlabel("Wavelength $\\lambda$ (nm)")
            plt.ylabel("Spectral Distribution ($W/m^2$)")
            # Re-setup cursor after clearing
            self._setup_cursor()
            # Restore cursor state if it was visible
            if self.cursor_visible and self.last_mouse_pos:
                self._update_cursor_position(self.last_mouse_pos[0], self.last_mouse_pos[1])
            self.update_status()
            self.fig.canvas.draw()
        except Exception as ex:
            if self.running:  # Only print if we're not shutting down
                print(f"Plot update error: {ex}")

    def _add_toolbar_buttons(self):
        """Add custom buttons to the toolbar"""
        if self.fig and hasattr(self.fig.canvas, 'manager') and self.fig.canvas.manager.toolmanager:
            tool_mgr = self.fig.canvas.manager.toolmanager
            tool_mgr.add_tool("refresh", RefreshTool, plot=self)
            tool_mgr.add_tool("oneshot", OneShotTool, plot=self)
            tool_mgr.add_tool("quick", QuickGraphTool, plot=self)
            tool_mgr.add_tool("power", PowerTool, plot=self)
            tool_mgr.add_tool("plot_save", PlotSaveTool, plot=self,
                              file_template=self.file_template)
            tool_mgr.add_tool("raw_save", RawSaveTool, plot=self,
                              file_template=self.file_template)

            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("plot_save"), "export")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("raw_save"), "export")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("refresh"), "refresh")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("oneshot"), "refresh")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("quick"), "refresh")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("power"), "power")

    def _setup_cursor(self):
        """Setup cursor tracking for easy reading of values on the graph"""
        try:
            # Create cursor dot
            self.cursor_dot = self.axes.plot([], [], 'ro', markersize=6,
                                             alpha=0.8, visible=False)[0]
            self.cursor_dot2 = self.axes.plot([], [], 'ro', markersize=4,
                                              alpha=0.8, visible=False)[0]
            # Create text annotation
            self.cursor_text = self.axes.annotate('', xy=(0, 0), xytext=(20, 20),
                                              textcoords="offset points",
                                              bbox={
                                                  'boxstyle': "round",
                                                  'fc': "white",
                                                  'alpha': 0.8
                                              },
                                              arrowprops={
                                                  'arrowstyle': "->",
                                                  'connectionstyle': "arc3,rad=0"
                                              },
                                              visible=False)

            # Connect mouse motion event
            self.fig.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
            self.fig.canvas.mpl_connect('axes_enter_event', self._on_axes_enter)
            self.fig.canvas.mpl_connect('axes_leave_event', self._on_axes_leave)
        except Exception:
            # Ignore cursor setup errors during shutdown
            pass

    def _update_cursor_position(self, x_pos, _y_pos):
        """Update cursor position and visibility"""
        try:
            if x_pos is not None and self.cursor_dot and self.cursor_text:
                # Find closest wavelength
                spd = self.data.to_spectral_distribution()
                wavelengths = np.array(spd.wavelengths)
                values = np.array(spd.values)

                # Find the closest point
                idx = np.argmin(np.abs(wavelengths - x_pos))
                closest_wl = wavelengths[idx]
                closest_val = values[idx]

                # Determine text position based on cursor location
                x_range = self.axes.get_xlim()
                x_mid = (x_range[0] + x_range[1]) / 2
                text_offset = (-100, 20) if closest_wl > x_mid else (20, 20)

                # Update cursor position
                self.cursor_dot.set_data([closest_wl], [closest_val])
                self.cursor_dot.set_color('white')
                self.cursor_dot.set_visible(self.cursor_visible)

                self.cursor_dot2.set_data([closest_wl], [closest_val])
                self.cursor_dot2.set_color('black')
                self.cursor_dot2.set_visible(self.cursor_visible)

                # Update text annotation
                self.cursor_text.xy = (closest_wl, closest_val)
                self.cursor_text.set_text(f'λ: {closest_wl:.1f}nm\nValue: {closest_val:.4f}')
                self.cursor_text.set_position(text_offset)
                self.cursor_text.set_visible(self.cursor_visible)
        except Exception:
            # Ignore cursor update errors during shutdown
            pass

    def update_status(self):
        """Set toolbar message"""
        toolbar = self.fig.canvas.manager.toolbar
        if self.data_status and self.data_status == 'ok':
            stamp = self.data.ts.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
            status = f'{self.data_status} ({stamp})'
        else:
            status = self.data_status
        toolbar.set_message(f'acquisition: {status}, exp: {self.data.time} ms')

    def _on_mouse_move(self, event):
        """Handle mouse movement"""
        try:
            self.update_status()
            if event.inaxes == self.axes:
                self.last_mouse_pos = (event.xdata, event.ydata)  # Store position
                self._update_cursor_position(event.xdata, event.ydata)
                if self.fig and self.fig.canvas:
                    self.fig.canvas.draw_idle()
        except Exception:
            # Ignore mouse events during shutdown
            pass

    def _on_axes_enter(self, _event):
        """Show cursor when entering axes"""
        try:
            self.cursor_visible = True
            if self.cursor_dot:
                self.cursor_dot.set_visible(True)
            if self.cursor_dot2:
                self.cursor_dot2.set_visible(True)
            if self.cursor_text:
                self.cursor_text.set_visible(True)
            self.update_status()
        except Exception:
            pass

    def _on_axes_leave(self, _event):
        """Hide cursor when leaving axes"""
        try:
            self.cursor_visible = False
            if self.cursor_dot:
                self.cursor_dot.set_visible(False)
            if self.cursor_dot2:
                self.cursor_dot2.set_visible(False)
            if self.cursor_text:
                self.cursor_text.set_visible(False)
            if self.fig and self.fig.canvas:
                self.fig.canvas.draw_idle()
            self.update_status()
        except Exception:
            pass

    def stop(self):
        """Stop the app (clean up)"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)  # Don't wait forever

        # Safely close matplotlib figure
        try:
            if self.fig:
                plt.close(self.fig)
                self.fig = None
        except Exception:
            pass  # Ignore errors during figure cleanup

if __name__ == "__main__":
    def parse_args():
        """Parse the arguments for the cli"""
        parser = argparse.ArgumentParser(description="TorchBearer spectrometer tool")

        # Required positional argument: input file
        parser.add_argument('input_device', help="Spectrometer device (/dev/ttyUSB0)")

        # Exposure: either 'auto' or integer milliseconds
        def exposure_type(value):
            err = "Exposure must be 'auto' or a positive integer (100..5000)"
            if value == 'auto':
                return value
            try:
                ivalue = int(value)
                if ivalue < 100 or ivalue > 5000:
                    raise argparse.ArgumentTypeError(err)
                return ivalue
            except ValueError as exc:
                raise argparse.ArgumentTypeError(err) from exc

        parser.add_argument(
            '-e', '--exposure',
            type=exposure_type,
            default='auto',
            help="Exposure time in milliseconds (100..5000) or 'auto' (default: auto)"
        )

        parser.add_argument(
            '-q', '--quick-graph',
            action='store_true',
            help="Enable quick graph mode"
        )

        parser.add_argument(
            '-o', '--oneshot',
            action='store_true',
            help="One shot mode (single good capture)"
        )

        default_template = 'spectrum-{timestamp_full}'
        parser.add_argument(
            '-f', '--file_template',
            default=default_template,
            help=f"File template (without .ext) for data export (default: {default_template})"
        )

        return parser.parse_args()

    argv = parse_args()

    SPECTROMETER = None
    try:
        SPECTROMETER = spectrometer.Spectrometer(argv.input_device)
    except Exception as spec_ex:
        print(f"Couldn't init spectrometer: {spec_ex}")
        sys.exit(1)

    atexit.register(SPECTROMETER.cleanup)

    def signal_handler(_signum, _frame):
        """Signal handler to trigger cleanup"""
        print("\nReceived interrupt signal, shutting down gracefully...")
        SPECTROMETER.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    basic_info = SPECTROMETER.get_basic_info()
    if not basic_info['device_id'].startswith('Y'):
        print(f'Warning: only tested on Y21B*, this is {basic_info["device_id"]}')

    def is_ok(result):
        """Bool to string with extra nonsense on top, pylint"""
        return "success" if result else "failure"
    if argv.exposure == 'auto':
        if basic_info['exposure_mode'] != protocol.ExposureMode.AUTOMATIC:
            print('Setting auto mode:',
                  is_ok(SPECTROMETER.set_exposure_mode(protocol.ExposureMode.AUTOMATIC)))
        else:
            print('Spectrometer already in auto mode.')
    else:
        if basic_info['exposure_mode'] != protocol.ExposureMode.MANUAL:
            print('Setting manual mode:',
                  is_ok(SPECTROMETER.set_exposure_mode(protocol.ExposureMode.MANUAL)))
        else:
            print('Spectrometer already in manual mode.')
        if basic_info['exposure_value'] != argv.exposure * 1000:
            print('Setting exposure value:',
                  is_ok(SPECTROMETER.set_exposure_value(argv.exposure * 1000)))
        else:
            print(f'Spectrometer already has exposure value of {argv.exposure} ms.')

    print("Exposure mode:", SPECTROMETER.get_exposure_mode())
    print("Exposure value:", SPECTROMETER.get_exposure_value(), 'μs')

    basic_info = SPECTROMETER.get_basic_info()
    print("Device basic info: ")
    pprint.pprint(basic_info)

    app = RefreshableSpectralPlot(spectrometer.Spectrum.initial(basic_info['range']),
                                  refresh_func=SPECTROMETER.stream_data,
                                  quick_graph=argv.quick_graph,
                                  oneshot=argv.oneshot,
                                  file_template=argv.file_template)
    app.start_plot()

sys.exit(0)
