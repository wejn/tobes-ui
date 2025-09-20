"""The main plot window for the application"""

from datetime import datetime, timedelta
import queue
import threading
import time
from typing import Any, NamedTuple, Type
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
from matplotlib.backend_tools import ToolBase
import matplotlib.text
import numpy as np

from .cursors import SingleGraphCursor, OverlayGraphCursor
from .logger import LOGGER
from .spectrometer import ExposureStatus
from .types import GraphType, RefreshType
from .tools import (
    RefreshTool, OneShotTool, HistoryStartTool, HistoryBackTool, HistoryForwardTool,
    HistoryEndTool, GraphSelectTool, FixYRangeGlobalTool, FixYRangeTool, LogYScaleTool,
    PowerTool, PlotSaveTool, RawSaveTool, NameTool, RemoveTool, ClearTool, VisXTool,
    SpectrumOverlayTool)

# pylint: disable=broad-exception-caught
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments
# pylint: disable=too-many-statements


class YAxisValues(NamedTuple):
    """Named tuple holding info about SpectralDistribution for Y axis (min, min positive, max)"""
    minimum: float
    minimum_positive: float
    maximum: float

    @classmethod
    def from_spd(cls, spd):
        """Get YAxisValues from a SpectralDistribution"""
        minimum = min(spd.values())
        minimum_positive = min(x for x in spd.values() if x > 0)
        maximum = max(spd.values())
        return cls(
                minimum=minimum,
                minimum_positive=minimum_positive,
                maximum=maximum)

    @classmethod
    def from_list(cls, values):
        """Get YAxisValues from a list of them (aggregate the min/pos/max)"""
        minimum = min(x.minimum for x in values)
        minimum_positive = min(x.minimum_positive for x in values)
        maximum = max(x.maximum for x in values)
        return cls(
                minimum=minimum,
                minimum_positive=minimum_positive,
                maximum=maximum)


class RefreshableSpectralPlot:
    """Refreshable plot (graph); basically main window of the app"""
    VISIBLE_SPECTRUM = range(380, 750)
    YLABEL = "Spectral Power Distribution"


    class GraphOverlay(NamedTuple):
        """Textual overlay message on the graph"""
        text: matplotlib.text.Text
        tag: str = None
        ttl: datetime = None


    def __init__(self, initial_data, refresh_func=None, graph_type=GraphType.SPECTRUM,
                 refresh_type=RefreshType.DISABLED, file_template=None, history_size=50):
        self._history = []
        self._history_yvals = []
        self._history_index = -1
        self.max_history_size = history_size
        self.running = False
        self.thread = None
        self.fig = None
        self.axes = None
        self.update_queue = queue.Queue()
        self._cursor = None
        self._last_mouse_pos = None  # Store last mouse position
        self._cursor_visible = False  # Track cursor visibility state
        self.refresh_func = refresh_func
        self.refresh_type = refresh_type
        self.data_refresh_issue = None
        self.graph_type = graph_type
        self.file_template = file_template
        self._overlay = None
        self.dirty = False
        self.fix_y_range = False
        self.fix_y_range_global = False
        self.log_y_scale = False
        self._fixed_y_global = None
        self._fixed_y = None
        self.vis_x = False
        self.spectrum_overlay = False

        # Load 'em all up
        if initial_data:
            for spectrum in initial_data:
                self.data = spectrum

    @property
    def name(self):
        """Name of current graph"""
        if self.data:
            return self.data.name
        return None

    @name.setter
    def name(self, value):
        """Setter for name"""
        if self.data:
            self.data.name = value

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

        yvals = YAxisValues.from_spd(new_data.spd)

        self._history.append(new_data)
        self._history_yvals.append(yvals)

        if len(self._history) > self.max_history_size:
            self._history.pop(0)
            self._history_yvals.pop(0)

        self._history_index = len(self._history) - 1
        self._fixed_y_global = YAxisValues.from_list(self._history_yvals)

    def remove_all_data(self):
        """Remove all data from history and view"""
        self._history = []
        self._history_yvals = []
        self._history_index = -1
        self._fixed_y_global = None
        self.dirty = True

    def remove_current_data(self):
        """Remove currently displayed data from history and view (if any)"""
        if not self.data:
            return
        self._history.pop(self._history_index)
        self._history_yvals.pop(self._history_index)
        if self._history_index > len(self._history) - 1:
            self._history_index = len(self._history) - 1
        if len(self._history_yvals) > 0:
            self._fixed_y_global = YAxisValues.from_list(self._history_yvals)
        else:
            self._fixed_y_global = None
        self.dirty = True

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
        self.make_overlay('Initializing...')

        self.update_status()
        self.fig.canvas.mpl_connect('close_event', self._on_close)

        plt.ion()
        plt.show(block=False)
        self._add_toolbar_buttons()

        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

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
                        self.expire_overlay()
                    self.fig.canvas.flush_events()
                    time.sleep(.1)
                except Exception as ex:
                    LOGGER.debug("exception", exc_info=True)
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
                case ExposureStatus.NORMAL:
                    self.update_queue.put(data)
                    self.data_refresh_issue = None
                    if self.refresh_type == RefreshType.ONESHOT:
                        self.refresh_type = RefreshType.NONE

                case ExposureStatus.UNDER:
                    self.data_refresh_issue = ('Under-exposed\n' +
                                               f'Exp. time: {data.time:.01f}\n({now_str})')

                case ExposureStatus.OVER:
                    self.data_refresh_issue = ('Over-exposed\n' +
                                               f'Exp. time: {data.time:.01f}\n({now_str})')

                case _:
                    self.data_refresh_issue = f'Error:\n{data.status}\n({now_str})'

        return self._should_refresh()

    def _data_loop(self):
        """Background thread that generates new data throuh refresh func"""
        while self.running:
            try:
                time.sleep(0.1)
                if not self._should_refresh():
                    continue

                if self.refresh_func:
                    self.refresh_func(self._refresh_cb)
                else:
                    # Shouldn't happen
                    self.refresh_type = RefreshType.DISABLED
                    self.dirty = True
            except Exception:
                LOGGER.debug("exception", exc_info=True)
                # If we can't get new data, just continue
                if self.running:
                    break

    def make_overlay(self, text, tag=None, ttl=None):
        """Make graph overlay with given tag and time to live"""
        if self._overlay:
            self._overlay.text.remove()
        self._overlay = self.GraphOverlay(
                text=self.fig.text(
                    0.5, 0.5, text,
                    ha='center', va='center', fontsize=16, color='black',
                    bbox={"facecolor": 'white', "alpha": 0.9, "pad": 20}),
                tag=tag or '__unnamed__',
                ttl=datetime.now() + timedelta(seconds=ttl) if ttl else None)
        self.fig.canvas.draw()

    def trigger_oneshot(self):
        """Trigger oneshot refresh of the data"""
        if self.refresh_type != RefreshType.DISABLED:
            self.refresh_type = RefreshType.ONESHOT
            self.make_overlay('One-shot refreshing...')

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

    def clear_overlay(self, tag=None):
        """Remove existing overlay message (only if matches tag)"""
        if self._overlay:
            if not tag or (tag and tag == self._overlay.tag):
                self._overlay.text.remove()
                self._overlay = None
                if self.fig and self.fig.canvas:
                    self.fig.canvas.draw_idle()

    def expire_overlay(self):
        """Remove existing overlay message if expired"""
        if self._overlay:
            if self._overlay.ttl and datetime.now() >= self._overlay.ttl:
                self._overlay.text.remove()
                self._overlay = None
                if self.fig and self.fig.canvas:
                    self.fig.canvas.draw_idle()

    def _tweak_y_axis(self):
        """Tweak the y axis appearance and range based on config"""
        self.axes.autoscale(enable=True, axis='y')

        if self.log_y_scale and self.graph_type in [GraphType.LINE, GraphType.OVERLAY]:
            self.axes.set_yscale('log')
            logscale = True
        else:
            self.axes.set_ylim(bottom=0)
            self.axes.set_yscale('linear')
            logscale = False

        if self.fix_y_range and self._fixed_y is None:
            self._fixed_y = self._history_yvals[self._history_index]

        if self.fix_y_range_global:
            ylim = self._fixed_y_global
        elif self.fix_y_range:
            ylim = self._fixed_y
        else:
            ylim = None

        top_margin = 1.05 # scaler, 1.05 = +5%
        match self.graph_type:
            case GraphType.LINE:
                if ylim:
                    if logscale:
                        self.axes.set_ylim(ylim.minimum_positive, ylim.maximum * top_margin)
                    else:
                        self.axes.set_ylim(ylim.minimum, ylim.maximum * top_margin)
            case GraphType.SPECTRUM:
                # No logscale support (because the flame graph doesn't clip correctly)
                if ylim:
                    self.axes.set_ylim(ylim.minimum, ylim.maximum * top_margin)
            case GraphType.OVERLAY:
                ylim = self._fixed_y_global
                if logscale:
                    self.axes.set_ylim(ylim.minimum_positive, ylim.maximum * top_margin)
                else:
                    self.axes.set_ylim(ylim.minimum, ylim.maximum * top_margin)
            case _:
                pass

    def _graph_title(self, spd):
        """Title for the graph based on current name and Spectrum's name"""
        if self.data and self.data.name:
            return f'{self.data.name} ({spd.name})'
        return spd.name

    def _draw_graph(self):
        """Draw graph based on configuration"""

        spd = self.data.to_spectral_distribution()
        kwargs = {
                'annotate_kwargs': {'annotate':False},
                'transparent_background': False,
                'show': False,
                'axes': self.axes,
        }
        legend = None
        match self.graph_type:
            case GraphType.CIE1931:
                xy_point = XYZ_to_xy(sd_to_XYZ(spd))
                plot_planckian_locus_in_chromaticity_diagram_CIE1931(
                        {"X": xy_point}, title=self._graph_title(spd), **kwargs)
            case GraphType.CIE1960UCS:
                xy_point = XYZ_to_xy(sd_to_XYZ(spd))
                plot_planckian_locus_in_chromaticity_diagram_CIE1960UCS(
                        {"X": xy_point}, title=self._graph_title(spd), **kwargs)
            case GraphType.CIE1976UCS:
                xy_point = XYZ_to_xy(sd_to_XYZ(spd))
                plot_planckian_locus_in_chromaticity_diagram_CIE1976UCS(
                        {"X": xy_point}, title=self._graph_title(spd), **kwargs)
            case GraphType.TM30:
                xy_point = XYZ_to_xy(sd_to_XYZ(spd))
                cct = colour.temperature.xy_to_CCT(xy_point, method='daylight')
                spec = colour_fidelity_index_ANSIIESTM3018(spd)
                if cct < 1000 or cct > 10000 or spec < 50:
                    self.axes.axis('off')
                    self.axes.text(
                            0.5, 0.5,
                            f'$R_f$={spec:.2f} (need $\\geq 50$), CCT={cct:.0f} (need 1-10K)',
                            ha='center', va='center', fontsize=16, color='red',
                            bbox={"facecolor": 'white', "alpha": 0.9, "pad": 20})

                else:
                    plt.title(self._graph_title(spd))
                    spec_full = colour_fidelity_index_ANSIIESTM3018(spd, True)
                    kwargs.update({'hspace': CONSTANTS_COLOUR_STYLE.geometry.short / 2})
                    plot_colour_vector_graphic(spec_full, **kwargs)
            case GraphType.SPECTRUM:
                self.axes.set_aspect('auto')
                cmfs_data = {}
                cmfs_source = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
                use_range = self.VISIBLE_SPECTRUM if self.vis_x else self.data.wavelength_range
                for wavelength in range(
                    use_range.start,
                    use_range.stop + 1
                ):
                    cmfs_data[wavelength] = cmfs_source[wavelength]
                cmfs = colour.MultiSpectralDistributions(cmfs_data)
                colour.plotting.plot_single_sd(spd, cmfs, **kwargs)
                plt.xlabel("Wavelength $\\lambda$ (nm)")
                plt.ylabel(f'{self.YLABEL} ({self.data.y_axis})')
                plt.title(self._graph_title(spd))

                self._tweak_y_axis()
            case GraphType.OVERLAY:
                self.axes.set_aspect('auto')
                self.fig.tight_layout()
                plt.title('Overlay graph')
                for idx, graph in enumerate(self._history):
                    spd = graph.to_spectral_distribution()
                    self.axes.plot(list(spd.wavelengths),
                                   list(spd.values),
                                   label=f'{idx+1:>3}: {graph.name or "(no name)"}')
                legend = plt.legend(prop={'family': 'monospace'})
                current_text = legend.get_texts()[self._history_index]
                current_text.set_color('blue')
                plt.xlabel("Wavelength $\\lambda$ (nm)")
                plt.ylabel(f'{self.YLABEL} ({self.data.y_axis})')

                xstart = min(x.wavelength_range.start for x in self._history)
                xstop = max(x.wavelength_range.stop for x in self._history)
                if self.vis_x:
                    self.axes.set_xlim(self.VISIBLE_SPECTRUM.start, self.VISIBLE_SPECTRUM.stop + 1)
                else:
                    self.axes.set_xlim(xstart, xstop)
                self._tweak_y_axis()

                self.fig.tight_layout()
                self.fig.figure.subplots_adjust(
                        hspace=CONSTANTS_COLOUR_STYLE.geometry.short / 2)
            case _:
                # GraphType.LINE goes here, too
                self.axes.set_aspect('auto')
                self.fig.tight_layout()
                plt.title(self._graph_title(spd))
                self.axes.plot(list(spd.wavelengths),
                             list(spd.values),
                             label='Spectral Distribution')
                plt.xlabel("Wavelength $\\lambda$ (nm)")
                plt.ylabel(f'{self.YLABEL} ({self.data.y_axis})')

                wl_range = self.data.wavelength_range
                if self.vis_x:
                    self.axes.set_xlim(self.VISIBLE_SPECTRUM.start, self.VISIBLE_SPECTRUM.stop + 1)
                else:
                    self.axes.set_xlim(wl_range.start, wl_range.stop)

                self._tweak_y_axis()

                self.fig.tight_layout()
                self.fig.figure.subplots_adjust(
                        hspace=CONSTANTS_COLOUR_STYLE.geometry.short / 2)

        # Re-setup cursor after clearing
        self._setup_cursor(legend)

        # Restore cursor state if it was visible
        if self._cursor_visible and self._last_mouse_pos:
            self._update_cursor_position(self._last_mouse_pos[0], self._last_mouse_pos[1])
            if self._cursor:
                self._cursor.set_visible()

        # Plop on the sensitivities overlay
        if self.spectrum_overlay:
            self._setup_spectrum_overlay()

    def update_plot(self):
        """Update plot in main thread"""
        try:

            if self.data:
                if self.refresh_type != RefreshType.CONTINUOUS:
                    self.make_overlay('Redrawing...')
                    self.fig.canvas.flush_events()
                self.axes.clear()
                self.clear_overlay()
                self._draw_graph()
            else:
                self.axes.clear()
                self.axes.set_axis_off()
                if self._should_refresh():
                    self.make_overlay('Loading data...')
                else:
                    self.make_overlay('No data.')

            self.update_status()
            self.fig.canvas.draw()
        except Exception as ex:
            LOGGER.debug("exception", exc_info=True)
            if self.running:  # Only print if we're not shutting down
                print(f"Plot update error: {ex}")

    def _add_toolbar_buttons(self):
        """Add custom buttons to the toolbar"""
        if self.fig and hasattr(self.fig.canvas, 'manager') and self.fig.canvas.manager.toolmanager:
            class ToolDesc(NamedTuple):
                """Description of a single tool"""
                name: str
                group: str
                cls: Type[ToolBase]
                args: dict[str, Any] = {}
                trigger: Any = None

            def avoid_untoggle(event):
                """
                Avoid the member of the radio group getting untoggled.
                Changing to other is fine, though.
                """
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

            # Tool order matters -- that's how they end up on the bar
            all_tools = [
                    ToolDesc('name', 'export', NameTool),
                    ToolDesc('plot_save', 'export', PlotSaveTool,
                             {'file_template': self.file_template}),
                    ToolDesc('raw_save', 'export', RawSaveTool,
                             {'file_template': self.file_template}),
            ]

            if not self.refresh_type == RefreshType.DISABLED:
                all_tools += [
                    ToolDesc('refresh', 'refresh', RefreshTool),
                    ToolDesc('oneshot', 'refresh', OneShotTool),
                ]

            all_tools += [
                ToolDesc('remove', 'refresh', RemoveTool),
                ToolDesc('clear', 'refresh', ClearTool),

                ToolDesc('history_start', 'nav', HistoryStartTool),
                ToolDesc('history_back', 'nav', HistoryBackTool),
                ToolDesc('history_forward', 'nav', HistoryForwardTool),
                ToolDesc('history_end', 'nav', HistoryEndTool),

                ToolDesc('line', 'graph', GraphSelectTool,
                         {'graph_type': GraphType.LINE},
                         avoid_untoggle),
                ToolDesc('spectrum', 'graph', GraphSelectTool,
                         {'graph_type': GraphType.SPECTRUM},
                         avoid_untoggle),
                ToolDesc('cie1931', 'graph', GraphSelectTool,
                         {'graph_type': GraphType.CIE1931},
                         avoid_untoggle),
                ToolDesc('cie1960ucs', 'graph', GraphSelectTool,
                         {'graph_type': GraphType.CIE1960UCS},
                         avoid_untoggle),
                ToolDesc('cie1976ucs', 'graph', GraphSelectTool,
                         {'graph_type': GraphType.CIE1976UCS},
                         avoid_untoggle),
                ToolDesc('tm30', 'graph', GraphSelectTool,
                         {'graph_type': GraphType.TM30},
                         avoid_untoggle),
                ToolDesc('overlay', 'graph', GraphSelectTool,
                         {'graph_type': GraphType.OVERLAY},
                         avoid_untoggle),

                ToolDesc('yrange_fix', 'axes', FixYRangeTool),
                ToolDesc('yrange_global_fix', 'axes', FixYRangeGlobalTool),
                ToolDesc('log_yscale', 'axes', LogYScaleTool),
                ToolDesc('visx', 'axes', VisXTool),
                ToolDesc('spec_ovl', 'axes', SpectrumOverlayTool),

                ToolDesc('power', 'power', PowerTool),
            ]

            # Now do the dance...
            tool_mgr = self.fig.canvas.manager.toolmanager
            toolbar = self.fig.canvas.manager.toolbar
            for tool in all_tools:
                tool_mgr.add_tool(tool.name, tool.cls, plot=self, **tool.args)
                toolbar.add_tool(tool_mgr.get_tool(tool.name), tool.group)
                if tool.trigger:
                    tool_mgr.toolmanager_connect(f"tool_trigger_{tool.name}", tool.trigger)

    COLOR_RANGES = {
            # https://en.wikipedia.org/wiki/Visible_spectrum
            range(380, 450): ('violet', '#7f00ff'),
            range(450, 485): ('blue', '#0000ff'),
            range(485, 500): ('cyan', '#00ffff'),
            range(500, 565): ('green', '#00ff00'),
            range(565, 590): ('yellow', '#ffff00'),
            range(590, 625): ('orange', '#ffa500'),
            range(625, 751): ('red', '#ff0000'), # +1 at the end
    }

    def _setup_spectrum_overlay(self):
        """Setup spectrum overlay (colors + photosensitivities)"""

        match self.graph_type:
            case GraphType.LINE | GraphType.OVERLAY:
                for rng, (_label, color) in self.COLOR_RANGES.items():
                    self.axes.axvspan(rng.start, rng.stop, color=color, alpha=0.1,
                                      label=color, lw=None)

                photopic_sd = colour.colorimetry.SDS_LEFS_PHOTOPIC[
                        'CIE 1924 Photopic Standard Observer']
                scotopic_sd = colour.colorimetry.SDS_LEFS_SCOTOPIC[
                        'CIE 1951 Scotopic Standard Observer']
                def melanopic_response(wavelength):
                    # 40nm stddev ~ broad response
                    return np.exp(-0.5 * ((wavelength - 480) / 40)**2)

                (xmin, xmax) = self.axes.get_xlim()
                (ymin, ymax) = self.axes.get_ylim()
                ymax = ymax * 0.999
                wls = np.arange(xmin, xmax + 1, 1)
                photopic = np.array([photopic_sd[w] for w in wls])
                scotopic = np.array([scotopic_sd[w] for w in wls])
                melanopic = melanopic_response(wls)
                photopic_norm = (photopic/np.max(photopic)) * (ymax-ymin) + ymin
                scotopic_norm = (scotopic/np.max(scotopic)) * (ymax-ymin) + ymin
                melanopic_norm = (melanopic/np.max(melanopic)) * (ymax - ymin) + ymin
                self.axes.plot(wls, photopic_norm, 'k:', label='photopic', alpha=0.1)
                self.axes.plot(wls, scotopic_norm, 'k-.', label='scotopic', alpha=0.1)
                self.axes.plot(wls, melanopic_norm, 'k--', label='melanopic', alpha=0.1)
            case _:
                pass

    def _setup_cursor(self, legend=None):
        """Setup cursor tracking for easy reading of values on the graph"""
        try:
            match self.graph_type:
                case GraphType.LINE | GraphType.SPECTRUM:
                    self._cursor = SingleGraphCursor(self.axes, self.data)
                case GraphType.OVERLAY:
                    self._cursor = OverlayGraphCursor(self.axes, self._history.copy(),
                                                      self._history_index, legend)
                case _:
                    self._cursor = None

            # Connect mouse motion event
            self.fig.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
            self.fig.canvas.mpl_connect('axes_enter_event', self._on_axes_enter)
            self.fig.canvas.mpl_connect('axes_leave_event', self._on_axes_leave)
        except Exception:
            LOGGER.debug("exception", exc_info=True)
            # Ignore cursor setup errors during shutdown

    def _update_cursor_position(self, x_pos, y_pos):
        """Update cursor position and visibility"""
        try:
            if x_pos is not None and self._cursor:
                self._cursor.update(x_pos, y_pos)
                if self.fig and self.fig.canvas:
                    self.fig.canvas.draw_idle()
        except Exception:
            LOGGER.debug("exception", exc_info=True)
            # Ignore cursor update errors during shutdown

    def update_status(self):
        """Set toolbar message"""
        toolbar = self.fig.canvas.manager.toolbar
        status = []

        if self.data_refresh_issue:
            if self.refresh_type == RefreshType.CONTINUOUS:
                self.make_overlay(f'Refresh problem: {self.data_refresh_issue}',
                                  tag='refresh_issue')
            else:
                self.data_refresh_issue = None
                self.clear_overlay('refresh_issue')

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
                if self._last_mouse_pos and int(self._last_mouse_pos[0]) == int(event.xdata):
                    return
                self._last_mouse_pos = (event.xdata, event.ydata)  # Store position
                self._update_cursor_position(event.xdata, event.ydata)
                if self.fig and self.fig.canvas:
                    self.fig.canvas.draw_idle()
        except Exception:
            LOGGER.debug("exception", exc_info=True)
            # Ignore mouse events during shutdown

    def _on_axes_enter(self, _event):
        """Show cursor when entering axes"""
        try:
            if self._cursor:
                self._cursor.set_visible()
            self._cursor_visible = True
            self.update_status()

            if self.fig and self.fig.canvas:
                self.fig.canvas.draw_idle()
        except Exception:
            LOGGER.debug("exception", exc_info=True)

    def _on_axes_leave(self, _event):
        """Hide cursor when leaving axes"""
        try:
            if self._cursor:
                self._cursor.set_visible(False)
            self._cursor_visible = False

            self.update_status()

            if self.fig and self.fig.canvas:
                self.fig.canvas.draw_idle()
        except Exception:
            LOGGER.debug("exception", exc_info=True)

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
            LOGGER.debug("exception", exc_info=True)
            # Ignore errors during figure cleanup
