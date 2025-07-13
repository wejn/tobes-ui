"""Cursors for the plot window"""

# pylint: disable=too-many-instance-attributes

class SingleGraphCursor:
    """Cursor on a single-plot graph (line, spectrum)"""
    def __init__(self, axes, data):
        self._axes = axes
        self._visible = False
        self._dot = self._axes.plot([], [], 'ro', markersize=6, alpha=0.8, visible=False)[0]
        self._dot.set_color('white')
        self._dot2 = self._axes.plot([], [], 'ro', markersize=4, alpha=0.8, visible=False)[0]
        self._dot2.set_color('black')
        self._annot = self._axes.annotate(
                '', xy=(0, 0), xytext=(20, 20),
                textcoords="offset points",
                bbox={
                    'boxstyle': "round",
                    'fc': "white",
                    'alpha': 0.8,
                },
                arrowprops={
                    'arrowstyle': "->",
                    'connectionstyle': "arc3,rad=0",
                    'visible': False,
                },
                visible=False)
        self._spd = data.to_spectral_distribution()

    def update(self, x_pos, _y_pos):
        """Update the cursor based on position"""
        # Find closest wavelength
        # Find the closest point
        closest_wl = int(x_pos)
        closest_val = self._spd[closest_wl]

        # Determine text position based on cursor location
        x_range = self._axes.get_xlim()
        x_mid = (x_range[0] + x_range[1]) / 2
        text_offset = (-78, 10) if closest_wl > x_mid else (10, 10)
        y_range = self._axes.get_ylim()
        y_mid = (y_range[0] + y_range[1]) / 2
        if closest_val > y_mid:
            text_offset = (text_offset[0], -25)

        # Update cursor position
        self._dot.set_data([closest_wl], [closest_val])

        self._dot2.set_data([closest_wl], [closest_val])

        # Update text annotation
        self._annot.xy = (closest_wl, closest_val)
        self._annot.set_text(f'λ: {closest_wl:.1f}nm\nValue: {closest_val:.4f}')
        self._annot.set_position(text_offset)

    def set_visible(self, visible=True):
        """Set visibility of the cursor"""
        self._visible = visible
        if self._dot:
            self._dot.set_visible(visible)
        if self._dot2:
            self._dot2.set_visible(visible)
        if self._annot:
            self._annot.set_visible(visible)


class OverlayGraphCursor:
    """Cursor on the overlay graph"""
    def __init__(self, axes, all_data, index, legend):
        self._axes = axes
        self._visible = False
        self._dot = self._axes.plot([], [], 'ro', markersize=6, alpha=0.8, visible=False)[0]
        self._dot.set_color('white')
        self._dot2 = self._axes.plot([], [], 'ro', markersize=4, alpha=0.8, visible=False)[0]
        self._dot2.set_color('black')
        self._axvline = self._axes.axvline(
                x=0, color='k', linestyle='--', linewidth=1, visible=False)
        self._annot = self._axes.annotate(
                '', xy=(0, 0), xytext=(20, 20),
                textcoords="offset points",
                bbox={
                    'boxstyle': "round",
                    'fc': "white",
                    'alpha': 0.8,
                },
                arrowprops={
                    'arrowstyle': "->",
                    'connectionstyle': "arc3,rad=0",
                    'visible': False,
                },
                visible=False)
        self._spd = all_data[index].to_spectral_distribution()
        self._all_data = all_data
        self._index = index
        self._legend = legend

        self._spds = []
        self._labels = []
        for idx, graph in enumerate(all_data):
            self._spds.append(graph.to_spectral_distribution())
            self._labels.append(f'{idx+1:>3}: {graph.name or "(no name)"}')

        # left-align to max length
        maxlabel = max(len(x) for x in self._labels)
        self._labels = [f'{x:<{maxlabel}}' for x in self._labels]

        # max value
        self._maxval = max(max(spd.values) for spd in self._spds)
        self._maxval_size = len(str(int(self._maxval)))

    def update(self, x_pos, _y_pos):
        """Update the cursor based on position"""
        # Find closest wavelength
        # Find the closest point
        closest_wl = int(x_pos)
        closest_val = self._spd[closest_wl]

        # Determine text position based on cursor location
        x_range = self._axes.get_xlim()
        x_mid = (x_range[0] + x_range[1]) / 2
        text_offset = (-78, 10) if closest_wl > x_mid else (10, 10)
        y_range = self._axes.get_ylim()
        y_mid = (y_range[0] + y_range[1]) / 2
        if closest_val > y_mid:
            text_offset = (text_offset[0], -25)

        # Update cursor position
        self._dot.set_data([closest_wl], [closest_val])
        self._dot2.set_data([closest_wl], [closest_val])
        self._axvline.set_xdata([closest_wl, closest_wl])

        # Update text annotation
        self._annot.xy = (closest_wl, closest_val)
        self._annot.set_text(f'λ: {closest_wl:.1f}nm\nValue: {closest_val:.4f}')
        self._annot.set_position(text_offset)

        # Update legend
        texts = self._legend.get_texts()
        mvs = self._maxval_size + 6 # 4 decimals, dot, sign
        if self._legend:
            for idx, spd in enumerate(self._spds):
                if self._index == idx:
                    # Reference
                    addon = f' {spd[closest_wl]:> {mvs}.4f} (   ref   )'
                else:
                    if closest_val == 0.0:
                        # Uncomparable (reference is zero)
                        addon = f' {spd[closest_wl]:> {mvs}.4f} (   n/a   )'
                    else:
                        perc = (self._spds[idx][closest_wl] / closest_val - 1) * 100.0
                        if -1000.0 < perc < 1000.0:
                            # Reasonable range -> straight %
                            addon = f' {spd[closest_wl]:> {mvs}.4f} ({perc:>+8.1f}%)'
                        else:
                            # Huge difference -> sci notation %
                            addon = f' {spd[closest_wl]:> {mvs}.4f} ({perc:>+8.1e}%)'
                texts[idx].set_text(self._labels[idx] + addon)

    def set_visible(self, visible=True):
        """Set visibility of the cursor"""
        self._visible = visible
        if self._dot:
            self._dot.set_visible(visible)
        if self._dot2:
            self._dot2.set_visible(visible)
        if self._axvline:
            self._axvline.set_visible(visible)
        if self._annot:
            self._annot.set_visible(visible)
