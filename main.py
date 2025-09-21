"""Nice UI for TorchBearer Spectrometer"""

# pylint: disable=too-many-statements,too-many-branches

import argparse
import atexit
import json
import logging
import pprint
import signal
import sys

import matplotlib
from matplotlib.backend_tools import default_toolbar_tools

from tobes_ui.loader import Loader
import tobes_ui.loaders
from tobes_ui.logger import LogLevel, configure_logging, LOGGER
from tobes_ui.plot import RefreshableSpectralPlot
from tobes_ui.spectrometer import ExposureMode, Spectrometer
import tobes_ui.spectrometers
from tobes_ui.types import GraphType, RefreshType

# pylint: disable=broad-exception-caught

if __name__ == "__main__":
    # Remove all tools by default (ouch)
    default_toolbar_tools.clear()

    def parse_args():
        """Parse the arguments for the cli"""
        parser = argparse.ArgumentParser(description="TorchBearer spectrometer tool")

        # Somewhat optional argument: input file
        types =  ', '.join(Spectrometer.spectrometer_types())
        parser.add_argument('input_device', nargs='?', default=None,
                            help=("Spectrometer device (dev:string); " +
                                  "; e.g. /dev/ttyUSB0, or type:/dev/foo (" +
                                  f"registered types: {types})"))

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
            '-b', '--backends',
            action='store_true',
            help="List all spectrometer backends"
        )

        parser.add_argument(
            '-L', '--loaders',
            action='store_true',
            help="List all file loaders"
        )

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
        template_with_name = '{name}-{timestamp_full}{graph_type}'
        parser.add_argument(
            '-f', '--file_template',
            default=default_template,
            help=f"File template (without .ext) for data export (default: '{default_template}')," +
                f" '{template_with_name}' might be also useful"
        )

        loaders= ", ".join(Loader.loader_types())
        parser.add_argument(
            '-d', '--data',
            default=None,
            nargs='*',
            help=f'File(s) to load for viewing (disables data refresh); loaders: {loaders}'
        )

        parser.add_argument(
            '-s', '--history-size',
            type=int,
            default=50,
            dest='history_size',
            help='Size of the measurement history (default: 50)'
        )

        def log_level(value):
            try:
                return LogLevel[value.upper()]
            except KeyError as exc:
                raise argparse.ArgumentTypeError(f"Invalid log level {value}") from exc

        parser.add_argument(
            '-l', '--log-level',
            type=log_level,
            default=LogLevel.WARN,
            help='Logging level to configure: {", ".join(e.name for e in LogLevel} (default WARN)'
        )

        parser.add_argument(
            '--log-file',
            type=str,
            default=None,
            help='Logfile to write to (defaults to none (=console))'
        )

        return parser.parse_args()

    def _init_meter(meter, argv):
        basic_info = meter.get_basic_info()
        if not basic_info.device_id.startswith('Y'):
            print(f'Warning: only tested on Y21B*, this is {basic_info.device_id}')

        def is_ok(result):
            """Bool to string with extra nonsense on top, pylint"""
            return "success" if result else "failure"
        if argv.exposure == 'auto':
            if basic_info.exposure_mode != ExposureMode.AUTOMATIC:
                print('Setting auto mode:',
                      is_ok(meter.set_exposure_mode(ExposureMode.AUTOMATIC)))
            else:
                print('Spectrometer already in auto mode.')
        else:
            if basic_info.exposure_mode != ExposureMode.MANUAL:
                print('Setting manual mode:',
                      is_ok(meter.set_exposure_mode(ExposureMode.MANUAL)))
            else:
                print('Spectrometer already in manual mode.')
            exposure_time_us = int(argv.exposure * 1000)
            if basic_info.time != exposure_time_us:
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

        configure_logging(argv.log_level, argv.log_file)
        print(f'Logging for tobes-ui configured at: {argv.log_level}')

        if argv.backends:
            print("Available backends:")
            types =  ', '.join(Spectrometer.spectrometer_types())
            print(types)
            print("")

            u_b = tobes_ui.spectrometers.failed_plugins()
            if u_b:
                print("Unavailable backends:")
                for name, reason in u_b.items():
                    print(f"{name}:\n\t{reason}")
            sys.exit(0)

        if argv.loaders:
            print("Available loaders:")
            types =  ', '.join(Loader.loader_types())
            print(types)
            print("")

            u_l = tobes_ui.loaders.failed_plugins()
            if u_l:
                print("Unavailable loaders:")
                for name, reason in u_l.items():
                    print(f"{name}:\n\t{reason}")
            sys.exit(0)

        if argv.input_device:
            try:
                meter = Spectrometer.create(argv.input_device)
            except Exception as spec_ex:
                LOGGER.debug("exception", exc_info=True)
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

            def usr1_handler(_signum, _frame):
                """USR1 signal handler -- enable debug logging"""
                print('enabling debug logging...')
                LOGGER.setLevel(logging.DEBUG)

            if 'SIGUSR1' in dir(signal):
                # Doesn't work on windows
                signal.signal(signal.SIGUSR1, usr1_handler)

            _init_meter(meter, argv)
        else:
            meter = None

        data = []
        if argv.data:
            for filename in argv.data:
                try:
                    data.append(Loader.load(filename))
                except (OSError, ValueError, json.decoder.JSONDecodeError) as exc:
                    print(f"File '{filename}' couldn't be parsed, skipping: {exc}")

        if not argv.input_device:
            refresh = RefreshType.DISABLED
        elif argv.no_refresh:
            refresh = RefreshType.NONE
        elif argv.oneshot:
            refresh = RefreshType.ONESHOT
        else:
            refresh = RefreshType.CONTINUOUS

        matplotlib.use("TkAgg")
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
