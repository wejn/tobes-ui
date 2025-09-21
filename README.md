# tobes-ui: **To**tally **Be**arable **S**pectrometer UI

This is a UI for [Torch Bearer](https://www.torchbearer.tech/)
Spectrometer (`Y21B7W10034CCPD`) that is available on Amazon
and AliExpress ([TB Store](https://www.aliexpress.com/store/1104401209)).

Forked from [ZoidTechnology/Torch-Bearer-Tools](https://github.com/ZoidTechnology/Torch-Bearer-Tools)[^1]
and improved (beyond recognition?).

It also supports importing `csv` from Hopoocolor HPCS-320, HPCS-330 spectrometers.

## Install

- `pipx install tobes-ui`

or:

- `pip install tobes-ui`

## Usage

```
$ python3 -m tobes_ui.main -h
usage: main.py [-h] [-b] [-L] [-e EXPOSURE] [-q | -t GRAPH_TYPE] [-o | -n]
               [-f FILE_TEMPLATE] [-d [DATA ...]] [-s HISTORY_SIZE] [-l LOG_LEVEL]
               [--log-file LOG_FILE]
               [input_device]

TorchBearer spectrometer tool

positional arguments:
  input_device          Spectrometer device (dev:string); ; e.g. /dev/ttyUSB0, or
                        type:/dev/foo (registered types: tb, torchbearer)

options:
  -h, --help            show this help message and exit
  -b, --backends        List all spectrometer backends
  -L, --loaders         List all file loaders
  -e EXPOSURE, --exposure EXPOSURE
                        Exposure time in milliseconds (0.1-5000) or 'auto' (default: auto)
  -q, --quick-graph     Enable quick (LINE) graph mode
  -t GRAPH_TYPE, --graph_type GRAPH_TYPE
                        Graph type (LINE, SPECTRUM, CIE1931, CIE1960UCS, CIE1976UCS, TM30,
                        OVERLAY) (default SPECTRUM)
  -o, --oneshot         One shot mode (single good capture)
  -n, --no-refresh      Start without refresh
  -f FILE_TEMPLATE, --file_template FILE_TEMPLATE
                        File template (without .ext) for data export (default:
                        'spectrum-{timestamp_full}{graph_type}'),
                        '{name}-{timestamp_full}{graph_type}' might be also useful
  -d [DATA ...], --data [DATA ...]
                        File(s) to load for viewing (disables data refresh); loaders: hpcs,
                        json
  -s HISTORY_SIZE, --history-size HISTORY_SIZE
                        Size of the measurement history (default: 50)
  -l LOG_LEVEL, --log-level LOG_LEVEL
                        Logging level to configure: {", ".join(e.name for e in LogLevel}
                        (default WARN)
  --log-file LOG_FILE   Logfile to write to (defaults to none (=console))
usage: main.py [-h] [-b] [-e EXPOSURE] [-q | -t GRAPH_TYPE] [-o | -n] [-f FILE_TEMPLATE]
               [-d [DATA ...]] [-s HISTORY_SIZE] [-l LOG_LEVEL] [--log-file LOG_FILE]
               [input_device]
```

My typical use is:

``` sh
# To gather new data
python3 -m tobes_ui.main /dev/ttyUSB0 -e auto -o
# or (if you use pipx): tobes-ui /dev/...

# To "replay" existing samples:
python3 -m tobes_ui.main -d examples/*.json
# or (if you use pipx): tobes-ui -d ...
```

The first invocation gives one-shot spectrum on auto exposure (from `/dev/ttyUSB0`):

![screenshot of live capture](https://github.com/wejn/tobes-ui/blob/master/pictures/oneshot.png)

Or, if you prefer, [screenshot of the CIE1976UCS locus](https://github.com/wejn/tobes-ui/blob/master/pictures/oneshot-cie1976ucs.png)
or [screenshot of the TM30 graph](https://github.com/wejn/tobes-ui/blob/master/pictures/oneshot-tm30.png).

The second invocation shows you replay of examples (no spectrometer needed!):

![screenshot of replay](https://github.com/wejn/tobes-ui/blob/master/pictures/replay.png)

![screenshot of replay overlay log](https://github.com/wejn/tobes-ui/blob/master/pictures/replay-overlay-log.png)

There are several icons on the toolbar:

| Icon | Key | Explanation |
|:---|:---:|:---|
| ![name](icons/name.png) | `Enter`, `A` | Name the current spectrum data |
| ![save](icons/plot_save.png) | `S` | Saves rendered graph as png |
| ![download](icons/raw_save.png) | `D` | Save raw data as json |
| ![refresh](icons/refresh.png) | `R` | Keep refreshing data |
| ![oneshot](icons/oneshot.png) | `1`, `O` | One good acquisition |
| ![remove](icons/remove.png) | `Delete`, `X` | Remove the current spectrum data _(from UI)_ |
| ![clear](icons/clear.png) | `-` | Remove all the spectrum data _(from UI)_ |
| ![history start](icons/hist_start.png) | `Home`, `H` | Go to start of history |
| ![history back](icons/hist_back.png) | `←`, `P` | Go to previous sample |
| ![history forward](icons/hist_forward.png) | `→`, `N` | Go to next sample |
| ![history start](icons/hist_start.png) | `End`, `E` | Go to end of history |
| ![line graph](icons/line_graph.png) | `Q`, `L` | Line graph |
| ![spectral graph](icons/spectrum_graph.png) | `C` | Spectrum graph _(slow to draw)_ |
| ![cie1931 locus](icons/cie1931_graph.png) | `3` | CIE1931 locus graph |
| ![cie1960UCS locus](icons/cie1960ucs_graph.png) | `6` | CIE1960UCS locus graph |
| ![cie1976UCS locus](icons/cie1976ucs_graph.png) | `7` | CIE1976UCS locus graph |
| ![tm30 graph](icons/tm30_graph.png) | `T` | TM30 graph |
| ![overlay graph](icons/overlay_graph.png) | `V` | Overlay graph -- all spectra at once |
| ![fix y range](icons/yrange_fix.png) | `Y` | Only line+spectrum: Fix Y-axis range based on current graph |
| ![global fix y range](icons/yrange_global_fix.png) | `G` | Only line+spectrum: Fix Y-axis range based on all graphs |
| ![log y axis](icons/log_yscale.png) | `K` | Only line+overlay: Use logarithmic Y-axis |
| ![visible spectrum](icons/visx.png) | `Z` | Only line, spectrum, overlay: Limit X axis to visible spectrum (380..750 nm)|
| ![spectrum overlay](icons/spec_ovl.png) | `\|` | Only line, overlay: Show spectrum + photosensitivities overlay |
| ![power](icons/power.png) | `Esc`, `Ctrl+Q` | Quit the app |

## Exported data

Sample exported data:

``` json
{
    "status": "normal",
    "exposure": "automatic",
    "time": 329.1,
    "spd": {
        "340": 0.0,
        "341": 0.0,
        "...": "......",
        "595": 0.013011,
        "596": 0.013095,
        "597": 0.013176,
        "598": 0.013251,
        "599": 0.013318,
        "600": 0.013385,
        "601": 0.01345,
        "602": 0.013515,
        "603": 0.013575,
        "604": 0.013621,
        "605": 0.013648,
        "...": "......",
        "995": 0.005143,
        "996": 0.005075,
        "997": 0.005119,
        "998": 0.004982,
        "999": 0.004944,
        "1000": 0.004859
    },
    "wavelength_range": [
        340,
        1000
    ],
    "wavelengths_raw": [
        340,
        341,
        "...",
        999,
        1000
    ],
    "spd_raw": [
        0.0,
        0.0,
        "......",
        0.013011,
        0.013095,
        0.013176,
        0.013251,
        0.013318,
        0.013385,
        0.01345,
        0.013515,
        0.013575,
        0.013621,
        0.013648,
        "......",
        0.005143,
        0.005075,
        0.005119,
        0.004982,
        0.004944,
        0.004859
    ],
    "ts": 1751704901.025932,
    "name": "my fancy spectrum",
    "y_axis": "$W\\cdot{}m^{-2}\\cdot{}nm^{-1}$",
    "device": "Y21B7W10034CCPD"
}
```

Meaning of the keys:

| Key | Type | Default | Meaning |
| --- | ---- | ------- | ------- |
| status | enum | **required** | Status of the exposure (normal, over, under) |
| exposure | enum | **required** | Type of the exposure (manual, automatic) |
| time | float | **required** | Time (ms) of the exposure |
| spd | dict[int, float] | **required** | Dictionary of wavelength: intensity |
| wavelength_range | range | from spd | Range of `spd` |
| wavelengths_raw | list[float] | None | Raw wavelengths (device-specific) |
| spd_raw | list[float] | None | Raw intensities (device-specific) |
| ts | unix ts | **required** | Time when the measurement took place |
| name | str | None | Human name for the measurement |
| y_axis | str | `"counts"` | Unit for the Y axis |
| device | str | None | Identifier of the device that took the measurement |

## License

GPLv3

[^1]: Discussed in the [Software Hacks Unlock Cheap
Spectrometer](https://hackaday.com/2025/03/31/software-hacks-unlock-cheap-spectrometer/)
article.
