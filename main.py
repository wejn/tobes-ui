"""Nice UI for TorchBearer Spectrometer"""

import argparse
import atexit
from datetime import datetime
from enum import Enum
import json
import os
import pprint
import queue
import signal
import sys
import threading
import time
import warnings

import colour
from colour.colorimetry import sd_to_XYZ
from colour.models import XYZ_to_xy
from colour.plotting import (
    CONSTANTS_COLOUR_STYLE,
    plot_planckian_locus_in_chromaticity_diagram_CIE1931,
    plot_planckian_locus_in_chromaticity_diagram_CIE1960UCS,
    plot_planckian_locus_in_chromaticity_diagram_CIE1976UCS,
)
from colour.plotting.tm3018.components import (
    plot_colour_vector_graphic
)
from colour.quality import colour_fidelity_index_ANSIIESTM3018
from matplotlib import pyplot as plt
from matplotlib.backend_bases import KeyEvent
from matplotlib.backend_managers import ToolManager
from matplotlib.backend_tools import ToolBase, ToolToggleBase, default_toolbar_tools
import numpy as np

import protocol
import spectrometer

# pylint: disable=broad-exception-caught
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments


class GraphType(Enum):
    """Defines graph type to display"""
    LINE = 1
    SPECTRUM = 2
    CIE1931 = 3
    CIE1960UCS = 4
    CIE1976UCS = 5
    TM30 = 6

    def __str__(self):
        """Convert to readable string"""
        return str(self.name).lower()


class RefreshType(Enum):
    """Defines active refresh"""
    DISABLED = 1
    NONE = 2
    ONESHOT = 3
    CONTINUOUS = 4

    def __str__(self):
        """Convert to readable string"""
        return str(self.name).lower()


class GraphSelectTool(ToolToggleBase):
    """Graph toggle for the toolbar"""
    radio_group = 'graph_select'

    def __init__(self, *args, plot, graph_type, **kwargs):
        self.plot = plot
        self.graph_type = graph_type
        self.default_toggled = self.plot.graph_type == graph_type
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/quick")
        match graph_type:
            case GraphType.LINE:
                self.description = 'Line graph (key: Q, L)'
                self.default_keymap = ['Q', 'q', 'L', 'l']
                self.image = os.path.join(script_dir, "icons/line_graph")
            case GraphType.SPECTRUM:
                self.description = 'Spectrum graph (key: C)'
                self.default_keymap = ['C', 'c']
                self.image = os.path.join(script_dir, "icons/spectrum_graph")
            case GraphType.CIE1931:
                self.description = 'CIE1931 locus graph (key: 3)'
                self.default_keymap = ['3']
                self.image = os.path.join(script_dir, "icons/cie1931_graph")
            case GraphType.CIE1960UCS:
                self.description = 'CIE1960UCS locus graph (key: 6)'
                self.default_keymap = ['6']
                self.image = os.path.join(script_dir, "icons/cie1960ucs_graph")
            case GraphType.CIE1976UCS:
                self.description = 'CIE1976UCS locus graph (key: 7)'
                self.default_keymap = ['7']
                self.image = os.path.join(script_dir, "icons/cie1976ucs_graph")
            case GraphType.TM30:
                self.description = 'TM30 graph (key: t)'
                self.default_keymap = ['t', 'T']
                self.image = os.path.join(script_dir, "icons/tm30_graph")
            case _:
                raise ValueError(f'weird graph type: {graph_type}')

        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        self.plot.switch_graph(self.graph_type)

    def disable(self, event=None):
        pass


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
                    'graph_type': '-' + str(self.plot.graph_type),
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
                    'graph_type': '',
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
        tool_mgr = self.plot.fig.canvas.manager.toolmanager
        refresh = tool_mgr.get_tool("refresh", warn=False)
        if refresh and refresh.toggled:
            tool_mgr.trigger_tool('refresh')

        self.plot.trigger_oneshot()


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
        self.default_toggled = self.plot.refresh_type == RefreshType.CONTINUOUS
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/refresh")
        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        if self.plot.refresh_type != RefreshType.DISABLED:
            self.plot.refresh_type = RefreshType.CONTINUOUS

    def disable(self, event=None):
        if self.plot.refresh_type != RefreshType.DISABLED:
            self.plot.refresh_type = RefreshType.NONE


class HistoryBackTool(ToolBase):
    """Go back in history"""
    description = 'Go back in history (key: ← || P)'
    default_keymap = ['left', 'p', 'P']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/hist_back")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.history_back()


class HistoryForwardTool(ToolBase):
    """Go forward in history"""
    description = 'Go forward in history (key: → || N)'
    default_keymap = ['right', 'n', 'N']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/hist_forward")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.history_forward()


class HistoryStartTool(ToolBase):
    """Go to start of history"""
    description = 'Go to start of history (key: home || H)'
    default_keymap = ['home', 'h', 'H']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/hist_start")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.history_start()


class HistoryEndTool(ToolBase):
    """Go to end of history"""
    description = 'Go to end of history (key: end || E)'
    default_keymap = ['end', 'e', 'E']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "icons/hist_end")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.history_end()


class RefreshableSpectralPlot:
    """Refreshable plot (graph); basically main window of the app"""
    def __init__(self, initial_data, refresh_func=None, graph_type=GraphType.SPECTRUM,
                 refresh_type=RefreshType.DISABLED, file_template=None, history_size=50):
        self._history = []
        self._history_index = -1
        self.max_history_size = history_size
        self.data = None
        # Load 'em all up
        if initial_data:
            for spectrum in initial_data:
                self.data = spectrum

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
        self.refresh_type = refresh_type
        self.data_refresh_issue = None
        self.graph_type = graph_type
        self.file_template = file_template
        self.error_text = None
        self.overlay_text = None
        self.dirty = False

    @property
    def data(self):
        """Currently selected data from history"""
        if self._history_index >= 0 and self._history_index < len(self._history):
            return self._history[self._history_index]
        return None

    @data.setter
    def data(self, new_data):
        """Add data to history"""
        if new_data is None:
            return

        self._history.append(new_data)
        if len(self._history) > self.max_history_size:
            self._history.pop(0)

        self._history_index = len(self._history) - 1

    WARNINGS_TO_IGNORE = [
            "Treat the new Tool classes introduced in v1.5 as experimental",
            "Key \\w+ changed from [a-z_]+ to [a-z_]+",
            "Attempting to set identical low and high ylims makes transformation" +
                " singular; automatically expanding.",
            '"OpenImageIO" related API features are not available, switching to "Imageio"!',
            # TM30 running on crap spectrum
            'Mean of empty slice .*',
            'Correlated colour temperature must be in domain.*'
    ]

    def start_plot(self):
        """Start the plotting in main thread; blocks"""
        for warning in self.WARNINGS_TO_IGNORE:
            warnings.filterwarnings("ignore", warning)
        plt.rcParams['toolbar'] = 'toolmanager'

        self.fig, self.axes = plt.subplots()
        self.axes.set_axis_off()
        self._make_overlay('Initializing...')

        self.update_status()
        self.fig.canvas.mpl_connect('close_event', self._on_close)

        plt.ion()
        plt.show(block=False)
        self._add_toolbar_buttons()

        plt.pause(0.1)

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
                    self.dirty = True
                except queue.Empty:
                    pass

                # Safely handle matplotlib events
                try:
                    if self.dirty:
                        self.dirty = False
                        self.update_plot()
                    else:
                        self.update_status()
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

    def _should_refresh(self):
        """Determines whether refresh is enabled"""
        return self.running and self.refresh_type in [RefreshType.ONESHOT, RefreshType.CONTINUOUS]

    def _refresh_cb(self, data):
        """Refresh callback that receives new spectral data, returns if further refreshes wanted"""
        if self._should_refresh():
            now_str = str(datetime.now()).split(' ')[1]
            match data.status:
                case protocol.ExposureStatus.NORMAL:
                    self.update_queue.put(data)
                    self.data_refresh_issue = None
                    if self.refresh_type == RefreshType.ONESHOT:
                        self.refresh_type = RefreshType.NONE

                case protocol.ExposureStatus.UNDER:
                    self.data_refresh_issue = f'under-exposed @ {data.time:.01f} ({now_str})'

                case protocol.ExposureStatus.OVER:
                    self.data_refresh_issue = f'over-exposed @ {data.time:.01f} ({now_str})'

                case _:
                    self.data_refresh_issue = f'error: {data.status} ({now_str})'

        return self._should_refresh()

    def _data_loop(self):
        """Background thread that generates new data throuh refresh func"""
        while self.running:
            try:
                time.sleep(1)
                if not self._should_refresh():
                    continue

                if self.refresh_func:
                    self.refresh_func(self._refresh_cb)
                else:
                    # Shouldn't happen
                    self.refresh_type = RefreshType.DISABLED
                    self.dirty = True
            except Exception:
                # If we can't get new data, just continue
                if self.running:
                    break

    def _make_overlay(self, text):
        if self.overlay_text:
            self.overlay_text.remove()
        self.overlay_text = self.fig.text(
                0.5, 0.5, text,
                ha='center', va='center', fontsize=16, color='black',
                bbox={"facecolor": 'white', "alpha": 0.9, "pad": 20})

    def trigger_oneshot(self):
        """Trigger oneshot refresh of the data"""
        if self.refresh_type != RefreshType.DISABLED:
            self.refresh_type = RefreshType.ONESHOT
            self._make_overlay('One-shot refreshing...')

    def history_back(self):
        """Go one step back in history"""
        if self._history_index > 0:
            if self.refresh_type == RefreshType.CONTINUOUS:
                tool_mgr = self.fig.canvas.manager.toolmanager
                tool_mgr.trigger_tool('refresh')

            self._history_index -= 1
            self.dirty = True

    def history_forward(self):
        """Go one step forward in history"""
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.dirty = True

    def history_start(self):
        """Go to start of history"""
        if self._history_index > 0:
            if self.refresh_type == RefreshType.CONTINUOUS:
                tool_mgr = self.fig.canvas.manager.toolmanager
                tool_mgr.trigger_tool('refresh')

            self._history_index = 0
            self.dirty = True

    def history_end(self):
        """Go to end of history"""
        if self._history_index < len(self._history) - 1:
            self._history_index = len(self._history) - 1
            self.dirty = True

    def switch_graph(self, graph_type: GraphType):
        """Switch graph to given type"""
        self.graph_type = graph_type
        self.dirty = True

    def _clear_overlays(self):
        """Remove existing overlay messages"""
        if self.overlay_text:
            self.overlay_text.remove()
            self.overlay_text = None
        if self.error_text:
            self.error_text.remove()
            self.error_text = None

    def _draw_graph(self):
        """Draw graph based on configuration"""

        spd = self.data.to_spectral_distribution()
        xy_point = XYZ_to_xy(sd_to_XYZ(spd))
        kwargs = {
                'annotate_kwargs': {'annotate':False},
                'transparent_background': False,
                'show': False,
                'axes': self.axes,
        }
        match self.graph_type:
            case GraphType.CIE1931:
                plot_planckian_locus_in_chromaticity_diagram_CIE1931(
                        {"X": xy_point}, title=spd.name, **kwargs)
            case GraphType.CIE1960UCS:
                plot_planckian_locus_in_chromaticity_diagram_CIE1960UCS(
                        {"X": xy_point}, title=spd.name, **kwargs)
            case GraphType.CIE1976UCS:
                plot_planckian_locus_in_chromaticity_diagram_CIE1976UCS(
                        {"X": xy_point}, title=spd.name, **kwargs)
            case GraphType.TM30:
                cct = colour.temperature.xy_to_CCT(xy_point, method='daylight')
                spec = colour_fidelity_index_ANSIIESTM3018(spd)
                if cct < 1000 or cct > 10000 or spec < 50:
                    self.axes.axis('off')
                    self.error_text = self.fig.text(
                            0.5, 0.5,
                            f'$R_f$={spec:.2f} (need $\\geq 50$), CCT={cct:.0f} (need 1-10K)',
                            ha='center', va='center', fontsize=16, color='red',
                            bbox={"facecolor": 'white', "alpha": 0.9, "pad": 20})

                else:
                    plt.title(f"{spd.display_name}")
                    spec_full = colour_fidelity_index_ANSIIESTM3018(spd, True)
                    kwargs.update({'hspace': CONSTANTS_COLOUR_STYLE.geometry.short / 2})
                    plot_colour_vector_graphic(spec_full, **kwargs)
            case GraphType.SPECTRUM:
                self.axes.set_aspect('auto')
                plt.title(f"{spd.display_name}")
                cmfs_data = {}
                cmfs_source = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
                for wavelength in range(
                    self.data.wavelength_range.start,
                    self.data.wavelength_range.stop + 1
                ):
                    cmfs_data[wavelength] = cmfs_source[wavelength]
                cmfs = colour.MultiSpectralDistributions(cmfs_data)
                colour.plotting.plot_single_sd(spd, cmfs, **kwargs)
                plt.xlabel("Wavelength $\\lambda$ (nm)")
                plt.ylabel("Spectral Distribution ($W/m^2$)")
            case _:
                # GraphType.LINE goes here, too
                self.axes.set_aspect('auto')
                self.fig.tight_layout()
                plt.title(f"{spd.display_name}")
                self.axes.plot(list(spd.wavelengths),
                             list(spd.values),
                             label='Spectral Distribution')
                plt.xlabel("Wavelength $\\lambda$ (nm)")
                plt.ylabel("Spectral Distribution ($W/m^2$)")
                self.fig.tight_layout()
                self.fig.figure.subplots_adjust(
                        hspace=CONSTANTS_COLOUR_STYLE.geometry.short / 2)

        # Re-setup cursor after clearing
        if not self.error_text:
            self._setup_cursor()

        # Restore cursor state if it was visible
        if self.cursor_visible and self.last_mouse_pos:
            self._update_cursor_position(self.last_mouse_pos[0], self.last_mouse_pos[1])

    def update_plot(self):
        """Update plot in main thread"""
        try:
            self._clear_overlays()
            self.axes.clear()

            if self.data:
                self._draw_graph()
            else:
                self.axes.set_axis_off()
                if self._should_refresh():
                    self._make_overlay('Loading data...')
                else:
                    self._make_overlay('No data.')

            self.update_status()
            self.fig.canvas.draw()
        except Exception as ex:
            if self.running:  # Only print if we're not shutting down
                print(f"Plot update error: {ex}")

    def _add_toolbar_buttons(self):
        """Add custom buttons to the toolbar"""
        if self.fig and hasattr(self.fig.canvas, 'manager') and self.fig.canvas.manager.toolmanager:
            tool_mgr = self.fig.canvas.manager.toolmanager
            if not self.refresh_type == RefreshType.DISABLED:
                tool_mgr.add_tool("refresh", RefreshTool, plot=self)
                tool_mgr.add_tool("oneshot", OneShotTool, plot=self)

            tool_mgr.add_tool("history_start", HistoryStartTool, plot=self)
            tool_mgr.add_tool("history_back", HistoryBackTool, plot=self)
            tool_mgr.add_tool("history_forward", HistoryForwardTool, plot=self)
            tool_mgr.add_tool("history_end", HistoryEndTool, plot=self)
            tool_mgr.add_tool("line", GraphSelectTool, plot=self,
                              graph_type=GraphType.LINE)
            tool_mgr.add_tool("spectrum", GraphSelectTool, plot=self,
                              graph_type=GraphType.SPECTRUM)
            tool_mgr.add_tool("cie1931", GraphSelectTool, plot=self,
                              graph_type=GraphType.CIE1931)
            tool_mgr.add_tool("cie1960ucs", GraphSelectTool, plot=self,
                              graph_type=GraphType.CIE1960UCS)
            tool_mgr.add_tool("cie1976ucs", GraphSelectTool, plot=self,
                              graph_type=GraphType.CIE1976UCS)
            tool_mgr.add_tool("tm30", GraphSelectTool, plot=self,
                              graph_type=GraphType.TM30)

            def avoid_untoggle(event):
                if isinstance(event.sender, ToolManager):
                    # coming from toolmanager, but key event (untoggle)
                    if isinstance(event.canvasevent, KeyEvent) and not event.tool.toggled:
                        if event.canvasevent.key in event.tool.default_keymap:
                            # and the trigger key is our key...
                            tool_mgr.trigger_tool(event.tool.name)
                else:
                    # not coming from toolmanager (that's the untoggle trigger)
                    if not event.tool.toggled:
                        # not toggled
                        tool_mgr.trigger_tool(event.tool.name)

            tool_mgr.toolmanager_connect("tool_trigger_line", avoid_untoggle)
            tool_mgr.toolmanager_connect("tool_trigger_spectrum", avoid_untoggle)
            tool_mgr.toolmanager_connect("tool_trigger_cie1931", avoid_untoggle)
            tool_mgr.toolmanager_connect("tool_trigger_cie1960ucs", avoid_untoggle)
            tool_mgr.toolmanager_connect("tool_trigger_cie1976ucs", avoid_untoggle)
            tool_mgr.toolmanager_connect("tool_trigger_tm30", avoid_untoggle)

            tool_mgr.add_tool("power", PowerTool, plot=self)
            tool_mgr.add_tool("plot_save", PlotSaveTool, plot=self,
                              file_template=self.file_template)
            tool_mgr.add_tool("raw_save", RawSaveTool, plot=self,
                              file_template=self.file_template)

            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("plot_save"), "export")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("raw_save"), "export")
            if not self.refresh_type == RefreshType.DISABLED:
                self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("refresh"), "refresh")
                self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("oneshot"), "refresh")

            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("history_start"), "nav")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("history_back"), "nav")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("history_forward"), "nav")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("history_end"), "nav")

            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("line"), "graph")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("spectrum"), "graph")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("cie1931"), "graph")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("cie1960ucs"), "graph")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("cie1976ucs"), "graph")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("tm30"), "graph")
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
        status = []

        if self.data_refresh_issue:
            status.append(self.data_refresh_issue)

        if self.data:
            status.append(f'exp: {self.data.time} ms')

        if self._history:
            status.append(f'hist: {self._history_index + 1}/{len(self._history)}')

        toolbar.set_message(' | '.join(status))

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

    def _on_close(self, _event):
        """Handle window being closed"""
        self.stop()

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
    # Remove all tools by default (ouch)
    default_toolbar_tools.clear()

    def parse_args():
        """Parse the arguments for the cli"""
        parser = argparse.ArgumentParser(description="TorchBearer spectrometer tool")

        # Somewhat optional argument: input file
        parser.add_argument('input_device', nargs='?', default=None,
                            help="Spectrometer device (/dev/ttyUSB0)")

        # Exposure: either 'auto' or number of milliseconds
        def exposure_type(value):
            err = "Exposure must be 'auto' or a positive number between 0.1 and 5000"
            if value == 'auto':
                return value
            try:
                fvalue = float(value)
                if fvalue < 0.1 or fvalue > 5000: # Minimum value accepted appears to be 0.1 ms
                    raise argparse.ArgumentTypeError(err)
                return fvalue
            except ValueError as exc:
                raise argparse.ArgumentTypeError(err) from exc

        parser.add_argument(
            '-e', '--exposure',
            type=exposure_type,
            default='auto',
            help="Exposure time in milliseconds (0.1-5000) or 'auto' (default: auto)"
        )

        graph_opts_group = parser.add_mutually_exclusive_group()

        graph_opts_group.add_argument(
            '-q', '--quick-graph',
            action='store_true',
            help="Enable quick (LINE) graph mode"
        )

        def graph_type(value):
            try:
                return GraphType[value.upper()]
            except KeyError as exc:
                raise argparse.ArgumentTypeError(f"Invalid graph type {value}") from exc

        graph_opts_group.add_argument(
            '-t', '--graph_type',
            type=graph_type,
            default=GraphType.SPECTRUM,
            help=f"Graph type ({', '.join([e.name for e in GraphType])}) (default SPECTRUM)"
        )

        refresh_opts_group = parser.add_mutually_exclusive_group()

        refresh_opts_group.add_argument(
            '-o', '--oneshot',
            action='store_true',
            help="One shot mode (single good capture)"
        )

        refresh_opts_group.add_argument(
            '-n', '--no-refresh',
            action='store_true',
            help="Start without refresh"
        )

        default_template = 'spectrum-{timestamp_full}{graph_type}'
        parser.add_argument(
            '-f', '--file_template',
            default=default_template,
            help=f"File template (without .ext) for data export (default: {default_template})"
        )

        parser.add_argument(
            '-d', '--data',
            default=None,
            nargs='*',
            help='JSON dump file(s) to load for viewing (disables data refresh)'
        )

        parser.add_argument(
            '-s', '--history-size',
            type=int,
            default=50,
            dest='history_size',
            help='Size of the measurement history (default: 50)'
        )

        return parser.parse_args()

    def _init_meter(meter, argv):
        basic_info = meter.get_basic_info()
        if not basic_info['device_id'].startswith('Y'):
            print(f'Warning: only tested on Y21B*, this is {basic_info["device_id"]}')

        def is_ok(result):
            """Bool to string with extra nonsense on top, pylint"""
            return "success" if result else "failure"
        if argv.exposure == 'auto':
            if basic_info['exposure_mode'] != protocol.ExposureMode.AUTOMATIC:
                print('Setting auto mode:',
                      is_ok(meter.set_exposure_mode(protocol.ExposureMode.AUTOMATIC)))
            else:
                print('Spectrometer already in auto mode.')
        else:
            if basic_info['exposure_mode'] != protocol.ExposureMode.MANUAL:
                print('Setting manual mode:',
                      is_ok(meter.set_exposure_mode(protocol.ExposureMode.MANUAL)))
            else:
                print('Spectrometer already in manual mode.')
            exposure_time_us = int(argv.exposure * 1000)
            if basic_info['exposure_value'] != exposure_time_us:
                print('Setting exposure value:',
                      is_ok(meter.set_exposure_value(exposure_time_us)))
            else:
                print(f'Spectrometer already has exposure value of {argv.exposure} ms.')

        print("Exposure mode:", meter.get_exposure_mode())
        print("Exposure value:", meter.get_exposure_value(), 'μs')

        basic_info = meter.get_basic_info()
        print("Device basic info: ")
        pprint.pprint(basic_info)


    def main():
        """Zee main(), like in C"""
        argv = parse_args()

        if argv.input_device:
            try:
                meter = spectrometer.Spectrometer(argv.input_device)
            except Exception as spec_ex:
                print(f"Couldn't init spectrometer: {spec_ex}")
                sys.exit(1)

            atexit.register(meter.cleanup)

            def signal_handler(_signum, _frame):
                """Signal handler to trigger cleanup"""
                print("\nReceived interrupt signal, shutting down gracefully...")
                meter.cleanup()
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            _init_meter(meter, argv)
        else:
            meter = None

        data = []
        if argv.data:
            for filename in argv.data:
                try:
                    data.append(spectrometer.Spectrum.from_file(filename))
                except (OSError, json.decoder.JSONDecodeError) as exc:
                    print(f"File '{filename}' couldn't be parsed, skipping: {exc}")

        if not argv.input_device:
            refresh = RefreshType.DISABLED
        elif argv.no_refresh:
            refresh = RefreshType.NONE
        elif argv.oneshot:
            refresh = RefreshType.ONESHOT
        else:
            refresh = RefreshType.CONTINUOUS

        app = RefreshableSpectralPlot(
                data,
                refresh_func=meter.stream_data if meter else None,
                graph_type=GraphType.LINE if argv.quick_graph else argv.graph_type,
                refresh_type=refresh,
                file_template=argv.file_template,
                history_size=argv.history_size)
        app.start_plot()

    main()
    sys.exit(0)
