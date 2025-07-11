"""The main plot window for the application"""

from datetime import datetime
import queue
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
import numpy as np

from .protocol import ExposureStatus
from .types import GraphType, RefreshType
from .tools import (
    RefreshTool, OneShotTool, HistoryStartTool, HistoryBackTool, HistoryForwardTool,
    HistoryEndTool, GraphSelectTool, FixYRangeGlobalTool, FixYRangeTool, LogYScaleTool,
    PowerTool, PlotSaveTool, RawSaveTool)

# pylint: disable=broad-exception-caught
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments
# pylint: disable=too-many-statements


class RefreshableSpectralPlot:
    """Refreshable plot (graph); basically main window of the app"""
    def __init__(self, initial_data, refresh_func=None, graph_type=GraphType.SPECTRUM,
                 refresh_type=RefreshType.DISABLED, file_template=None, history_size=50):
        self._history = []
        self._history_max = []
        self._history_index = -1
        self._fixed_y_global_lim = None
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
        self.fix_y_range = False
        self.fix_y_range_global = False
        self.fixed_y_lim = None
        self.log_y_scale = False

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

        new_max =  max(new_data.spd.values())

        self._history.append(new_data)
        self._history_max.append(new_max)

        if len(self._history) > self.max_history_size:
            self._history.pop(0)
            self._history_max.pop(0)

        self._history_index = len(self._history) - 1
        self._fixed_y_global_lim = (0, max(self._history_max))

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
                case ExposureStatus.NORMAL:
                    self.update_queue.put(data)
                    self.data_refresh_issue = None
                    if self.refresh_type == RefreshType.ONESHOT:
                        self.refresh_type = RefreshType.NONE

                case ExposureStatus.UNDER:
                    self.data_refresh_issue = f'under-exposed @ {data.time:.01f} ({now_str})'

                case ExposureStatus.OVER:
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

    def _tweak_y_axis(self, spd):
        if self.log_y_scale and self.graph_type == GraphType.LINE:
            self.axes.set_yscale('log')
        else:
            self.axes.set_yscale('linear')

        if self.graph_type in [GraphType.LINE, GraphType.SPECTRUM]:
            if self.fix_y_range_global:
                current_lim = (0, self._fixed_y_global_lim[1] * 1.05)
            elif self.fix_y_range:
                if self.fixed_y_lim is None:
                    self.fixed_y_lim = self.axes.get_ylim()

                current_lim = self.fixed_y_lim

            else:
                self.fixed_y_lim = None
                current_lim = None

            if current_lim:
                # log graph can't have min = 0
                if self.log_y_scale and self.graph_type == GraphType.LINE:
                    current_lim = self.fixed_y_lim
                    if self.log_y_scale and current_lim[0] <= 0:
                        all_values = np.array(list(spd.values))
                        positive_values = all_values[all_values > 0]
                        if positive_values.any():
                            min_val = np.min(positive_values)
                            current_lim = (min_val * 0.1, current_lim[1])

                self.axes.set_ylim(current_lim)

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
                plt.title(f"{spd.display_name}")

                self._tweak_y_axis(spd)

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

                vals = list(spd.wavelengths)
                self.axes.set_xlim((min(vals), max(vals)))
                self.axes.set_ylim((0, max(list(spd.values)) * 1.05))

                self._tweak_y_axis(spd)

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

            tool_mgr.add_tool("yrange_fix", FixYRangeTool, plot=self)
            tool_mgr.add_tool("yrange_global_fix", FixYRangeGlobalTool, plot=self)
            tool_mgr.add_tool("log_yscale", LogYScaleTool, plot=self)

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

            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("yrange_fix"), "axes")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("yrange_global_fix"), "axes")
            self.fig.canvas.manager.toolbar.add_tool(tool_mgr.get_tool("log_yscale"), "axes")

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
