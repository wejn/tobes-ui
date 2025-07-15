"""Matplotlib toolbar tools for the UI"""

import os
from tkinter import simpledialog

from matplotlib.backend_tools import ToolBase, ToolToggleBase

from .types import GraphType, RefreshType

# pylint: disable=too-many-arguments


class GraphSelectTool(ToolToggleBase):
    """Graph toggle for the toolbar"""
    radio_group = 'graph_select'

    def __init__(self, *args, plot, graph_type, **kwargs):
        self.plot = plot
        self.graph_type = graph_type
        self.default_toggled = self.plot.graph_type == graph_type
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/quick")
        match graph_type:
            case GraphType.LINE:
                self.description = 'Line graph\n(keys: Q, L)'
                self.default_keymap = ['Q', 'q', 'L', 'l']
                self.image = os.path.join(script_dir, "../icons/line_graph")
            case GraphType.SPECTRUM:
                self.description = 'Spectrum graph\n(key: C)'
                self.default_keymap = ['C', 'c']
                self.image = os.path.join(script_dir, "../icons/spectrum_graph")
            case GraphType.CIE1931:
                self.description = 'CIE1931 locus graph\n(key: 3)'
                self.default_keymap = ['3']
                self.image = os.path.join(script_dir, "../icons/cie1931_graph")
            case GraphType.CIE1960UCS:
                self.description = 'CIE1960UCS locus graph\n(key: 6)'
                self.default_keymap = ['6']
                self.image = os.path.join(script_dir, "../icons/cie1960ucs_graph")
            case GraphType.CIE1976UCS:
                self.description = 'CIE1976UCS locus graph\n(key: 7)'
                self.default_keymap = ['7']
                self.image = os.path.join(script_dir, "../icons/cie1976ucs_graph")
            case GraphType.TM30:
                self.description = 'TM30 graph\n(key: T)'
                self.default_keymap = ['t', 'T']
                self.image = os.path.join(script_dir, "../icons/tm30_graph")
            case GraphType.OVERLAY:
                self.description = 'Overlay graph\n(key: V)'
                self.default_keymap = ['v', 'V']
                self.image = os.path.join(script_dir, "../icons/overlay_graph")
            case _:
                raise ValueError(f'weird graph type: {graph_type}')

        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        self.plot.switch_graph(self.graph_type)

    def disable(self, event=None):
        pass


class PlotSaveTool(ToolBase):
    """Plot data save button for the toolbar"""
    description = 'Save plot data as png\n(key: S)'
    default_keymap = ['S', 's']

    def __init__(self, *args, plot, file_template, **kwargs):
        self.plot = plot
        self.file_template = file_template
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/plot_save")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        snap_time = self.plot.data.ts
        if not self.file_template:
            print("File template not defined, can't save")
        else:
            template_values = {
                    'name': self.plot.data.name or 'spectrum',
                    'graph_type': '-' + str(self.plot.graph_type),
                    'timestamp': str(int(snap_time.timestamp())),
                    'timestamp_full': str(snap_time.timestamp()),
                    'timestamp_human': str(snap_time),
            }
            filename = self.file_template.format(**template_values) + '.png'
            self.plot.fig.savefig(filename, format='png')
            print('Plot saved as:', filename)
            self.plot.make_overlay(f'Plot saved as:\n{filename}', tag='plot_save', ttl=3)


class RawSaveTool(ToolBase):
    """Raw data save button for the toolbar"""
    description = 'Save raw data as json\n(key: D)'
    default_keymap = ['D', 'd']

    def __init__(self, *args, plot, file_template, **kwargs):
        self.plot = plot
        self.file_template = file_template
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/raw_save")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        snap_time = self.plot.data.ts
        if not self.file_template:
            print(self.plot.data.to_json())
        else:
            template_values = {
                    'name': self.plot.data.name or 'spectrum',
                    'graph_type': '',
                    'timestamp': str(int(snap_time.timestamp())),
                    'timestamp_full': str(snap_time.timestamp()),
                    'timestamp_human': str(snap_time),
            }
            filename = self.file_template.format(**template_values) + '.json'
            with open(filename, 'w', encoding='utf-8') as file:
                file.write(self.plot.data.to_json())
            print('Raw data saved as:', filename)
            self.plot.make_overlay(f'Raw data saved as:\n{filename}', tag='raw_save', ttl=3)


class OneShotTool(ToolBase):
    """One Shot button for the toolbar"""
    description = 'One good acquisition\n(keys: 1, O)'
    default_keymap = ['1', 'O', 'o']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/oneshot")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        tool_mgr = self.plot.fig.canvas.manager.toolmanager
        refresh = tool_mgr.get_tool("refresh", warn=False)
        if refresh and refresh.toggled:
            tool_mgr.trigger_tool('refresh')

        self.plot.trigger_oneshot()


class PowerTool(ToolBase):
    """Quit button for the toolbar"""
    description = 'Quit application\n(keys: Esc, Ctrl+Q)'
    default_keymap = ['escape', 'ctrl+q', 'ctrl+Q']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/power")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.stop()


class RefreshTool(ToolToggleBase):
    """Refresh data toggle for the toolbar"""
    description = 'Keep refreshing data\n(key: R)'
    default_keymap = ['r', 'R']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        self.default_toggled = self.plot.refresh_type == RefreshType.CONTINUOUS
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/refresh")
        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        if self.plot.refresh_type != RefreshType.DISABLED:
            self.plot.refresh_type = RefreshType.CONTINUOUS

    def disable(self, event=None):
        if self.plot.refresh_type != RefreshType.DISABLED:
            self.plot.refresh_type = RefreshType.NONE


class HistoryBackTool(ToolBase):
    """Go back in history"""
    description = 'Go back in history\n(keys: ←, P)'
    default_keymap = ['left', 'p', 'P']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/hist_back")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.history_back()


class HistoryForwardTool(ToolBase):
    """Go forward in history"""
    description = 'Go forward in history\n(keys: →, N)'
    default_keymap = ['right', 'n', 'N']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/hist_forward")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.history_forward()


class HistoryStartTool(ToolBase):
    """Go to start of history"""
    description = 'Go to start of history\n(keys: Home, H)'
    default_keymap = ['home', 'h', 'H']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/hist_start")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.history_start()


class HistoryEndTool(ToolBase):
    """Go to end of history"""
    description = 'Go to end of history\n(keys: end, E)'
    default_keymap = ['end', 'e', 'E']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/hist_end")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.history_end()


class FixYRangeTool(ToolToggleBase):
    """Fix Y range of the plot"""
    description = ('Fix Y-axis range based on current graph\n' +
        '[only applies to line and spectrum graphs]\n(key: Y)')
    default_keymap = ['y', 'Y']
    radio_group = 'yrange_fixes'

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        self.default_toggled = self.plot.fix_y_range
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/yrange_fix")
        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        self.plot.fix_y_range = True
        self.plot.dirty = True # FIXME: this is expensive, can we do without?

    def disable(self, event=None):
        self.plot.fix_y_range = False
        self.plot.fixed_y_lim = None
        self.plot.dirty = True # FIXME: this is expensive, can we do without?


class FixYRangeGlobalTool(ToolToggleBase):
    """Fix Y range of the plot based on all graphs in history"""
    description = ('Fix Y-axis range based on all graphs\n' +
                   '[only applies to line and spectrum graphs]\n(key: G)')
    default_keymap = ['g', 'G']
    radio_group = 'yrange_fixes'

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        self.default_toggled = self.plot.fix_y_range_global
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/yrange_global_fix")
        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        self.plot.fix_y_range_global = True
        self.plot.dirty = True # FIXME: this is expensive, can we do without?

    def disable(self, event=None):
        self.plot.fix_y_range_global = False
        self.plot.dirty = True # FIXME: this is expensive, can we do without?


class LogYScaleTool(ToolToggleBase):
    """Switch Y axis to log scale"""
    description = ('Use logarithmic Y-axis\n' +
                   '[only applies to line and overlay graphs]\n(key: K)')
    default_keymap = ['k', 'K']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        self.default_toggled = self.plot.log_y_scale
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/log_yscale")
        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        self.plot.log_y_scale = True
        self.plot.dirty = True

    def disable(self, event=None):
        self.plot.log_y_scale = False
        self.plot.dirty = True


class VisXTool(ToolToggleBase):
    """Constrain X axis to visible spectrum"""
    description = ('Constrain X-axis to visible spectrum\n' +
                   '[only applies to line, spectrum, or overlay graphs]\n(key: Z)')
    default_keymap = ['z', 'Z']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        self.default_toggled = self.plot.log_y_scale
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/visx")
        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        self.plot.vis_x = True
        self.plot.dirty = True

    def disable(self, event=None):
        self.plot.vis_x = False
        self.plot.dirty = True


class NameTool(ToolBase):
    """Name the current spectrum data"""
    description = 'Name the current spectrum data\n(key: Enter, A)'
    default_keymap = ['enter', 'a', 'A']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/name")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        if not self.plot.data:
            return

        widget = self.plot.fig.canvas.get_tk_widget()
        result = simpledialog.askstring("Plot name", "Plot name:",
                                        parent=widget.winfo_toplevel(),
                                        initialvalue=self.plot.name)
        if result is not None:
            self.plot.name = result
            self.plot.dirty = True

        widget.focus_set()


class RemoveTool(ToolBase):
    """Remove the current spectrum data"""
    description = 'Remove the current spectrum data\n(key: delete, X)'
    default_keymap = ['delete', 'x', 'X']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/remove")
        super().__init__(*args, **kwargs)

    def trigger(self, *_args, **_kwargs):
        self.plot.remove_current_data()


class ClearTool(ToolBase):
    """Clear all spectrum data"""
    description = 'Clear all spectrum data\n(key: -)'
    default_keymap = ['-', '_']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/clear")
        super().__init__(*args, **kwargs)
    
    def trigger(self, *_args, **_kwargs):
        self.plot.remove_all_data()


class SpectrumOverlayTool(ToolToggleBase):
    """Show spectrum + sensitivities overlay"""
    description = ('Show spectrum + photosensitivities overlay\n' +
                   '[only applies to line or overlay graphs]\n(key: |)')
    default_keymap = ['|']

    def __init__(self, *args, plot, **kwargs):
        self.plot = plot
        self.default_toggled = self.plot.log_y_scale
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image = os.path.join(script_dir, "../icons/spec_ovl")
        super().__init__(*args, **kwargs)

    def enable(self, event=None):
        self.plot.spectrum_overlay = True
        self.plot.dirty = True

    def disable(self, event=None):
        self.plot.spectrum_overlay = False
        self.plot.dirty = True
