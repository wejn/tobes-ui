#!/usr/bin/env python3
"""Capture utility for Ocean Optics spectrometer, dumps tobes json"""

# pylint: disable=invalid-name
# pylint: disable=duplicate-code

import argparse
from datetime import datetime
import sys
import textwrap

import numpy as np
from scipy.interpolate import interp1d
import seabreeze.spectrometers as sb
import matplotlib.pyplot as plt

from tobes_ui.logger import LogLevel, configure_logging, LOGGER
from tobes_ui.protocol import ExposureMode, ExposureStatus
from tobes_ui.spectrometer import Spectrum

def spd_with_auto_exposure(spectrometer, min_time, max_time, min_step=1000,
                           correct_dark_counts=False,
                           correct_nonlinearity=False):
    """Get spectral distribution in auto exposure mode (within limits)"""
    hw_min, hw_max = spectrometer.integration_time_micros_limits
    if min_time < hw_min:
        low = hw_min
    else:
        low = min_time
    if max_time > hw_max:
        high = hw_max
    else:
        high = max_time

    data = None

    def is_overexposed(intensities):
        return len([1 for v in intensities if v > spectrometer.max_intensity * 0.9]) > 0

    while data is None or high - low > min_step:
        mid = (low + high) / 2.0
        spectrometer.integration_time_micros(mid)
        wl, i = spectrometer.spectrum(correct_dark_counts=correct_dark_counts,
                                      correct_nonlinearity=correct_nonlinearity)
        data = [wl, i]

        if is_overexposed(i):
            LOGGER.debug("Over-exposed at %.3f", mid)
            high = mid  # Too bright, decrease time
        else:
            LOGGER.debug("Good exposure at %.3f", mid)
            low = mid

    LOGGER.debug("Final exposure at %.3f", mid)
    return mid/1000.0, *data


if __name__ == "__main__":

    def parse_args():
        """Parse the arguments for the cli"""
        parser = argparse.ArgumentParser(description="Ocean spectrometer capture tool")

        # Exposure: either 'auto' or number of milliseconds
        def exposure_type(value):
            pn = "must be a positive number between 1 and 655350"
            err = 'auto exp must be in format: auto:min:max'
            if value == 'auto':
                return [1, 2000]
            if value.startswith('auto:'):
                try:
                    _auto, mi, ma = value.split(':', 3)
                except ValueError as exc:
                    raise argparse.ArgumentTypeError(err) from exc
                try:
                    mif = float(mi)
                    if mif < 1 or mif > 655350:
                        raise argparse.ArgumentTypeError(f'min {pn}')
                    maf = float(ma)
                    if maf < 1 or maf > 655350:
                        raise argparse.ArgumentTypeError(f'max {pn}')
                    return [mif, maf]
                except ValueError as exc:
                    raise argparse.ArgumentTypeError(err) from exc
            try:
                fvalue = float(value)
                if fvalue < 1 or fvalue > 655350:
                    raise argparse.ArgumentTypeError(pn)
                return [fvalue, fvalue]
            except ValueError as exc:
                raise argparse.ArgumentTypeError(pn) from exc

        parser.add_argument(
            '-e', '--exposure',
            type=exposure_type,
            default=[1, 2000],
            help=("Exposure time in milliseconds (1-655350) or 'auto'"" or 'auto:min:max'"
                  " (default: auto:1:2000)")
        )

        parser.add_argument(
            '-c', '--correct-nonlinearity',
            action='store_true',
            help="Correct non-linearity"
        )

        parser.add_argument(
            '-d', '--correct-dark-counts',
            action='store_true',
            help="Correct dark counts"
        )

        parser.add_argument(
            '-a', '--correct-above-zero',
            action='store_true',
            help="Correct to have all values above zero"
        )

        parser.add_argument(
            '-m', '--max',
            type=float,
            default=None,
            help='Scale to given max (default: do not)'
        )

        parser.add_argument(
            '-n', '--name',
            type=str,
            default=None,
            help="Name of the capture"
        )

        default_template = 'spectrum-{timestamp_full}'
        template_with_name = '{name}-{timestamp_full}'
        parser.add_argument(
            '-f', '--file-template',
            default=default_template,
            help=f"File template (without .ext) for data export (default: '{default_template}')," +
                f" '{template_with_name}' might be also useful"
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

        parser.add_argument(
            '-p', '--plot',
            action='store_true',
            help="Plot the captured spectrum"
        )

        parser.add_argument(
            '-C', '--calibrate',
            action='store_true',
            help="Calibrate the spectrometer"
        )

        return parser.parse_args()

    def main():
        """Zee main(), like in C"""
        argv = parse_args()

        configure_logging(argv.log_level, argv.log_file)
        print(f'Logging for ocean-capture configured at: {argv.log_level}')

        try:
            spectrometer = sb.Spectrometer.from_first_available()
        except Exception: # pylint: disable=broad-exception-caught
            print("No spectrometer available")
            sys.exit(1)

        print("model:", spectrometer)
        print("int limits:", spectrometer.integration_time_micros_limits)
        print("pixels:", spectrometer.pixels)

        if argv.calibrate:
            if spectrometer.pixels != 2048:
                print(f"Sorry, I don't know how do deal with devices with {spectrometer.pixels} pixels.")
                sys.exit(1)

            print(textwrap.dedent("""

            =--------------=
            Calibration mode
            =--------------=

            """))
            try:
                input("Safely cover the slit, then press enter to begin.")
            except KeyboardInterrupt:
                sys.exit(1)

            wl = spectrometer.wavelengths()
            i = []
            for _ in range(3):
                i.append(np.array(spectrometer.intensities(correct_dark_counts=False, correct_nonlinearity=False)))

            i = np.mean(np.array(i), axis=0)


            # According to docs: 0-17 optical black, 18-19 not usable, 20-2047 active
            dark_pixels = i[0:18]
            usable = i[20:]

            dark_q25 = np.percentile(dark_pixels, 25)
            dark_q75 = np.percentile(dark_pixels, 75)
            iqr = dark_q75 - dark_q25
            weird_indexes = np.where((dark_pixels < dark_q25 - 1.5*iqr) | (dark_pixels > dark_q75+1.5*iqr))[0]
            if len(weird_indexes) > 0:
                print("Weird black pixel indexes detected!")
                print("indexes:", weird_indexes)
                print("vals:", [dark_pixels[i] for i in weird_indexes])
                print("dark avg:", np.mean(dark_pixels), "sd:", np.std(dark_pixels))
                print("usable avg:", np.mean(usable), "sd:", np.std(usable))
                corr_dark = np.delete(dark_pixels, weird_indexes)
                print("corrected dark avg:", np.mean(corr_dark), "sd:", np.std(corr_dark))
                try:
                    input(f"Enter to blacklist the {weird_indexes}, ^C to keep them.")
                except KeyboardInterrupt:
                    weird_indexes = []
                    print("")

            if len(weird_indexes) > 0:
                print("Dark pixels to blacklist:", weird_indexes)
            else:
                print("No dark pixels to blacklist.")

            final_dark = [dark_pixels[i] for i in range(0,18) if i not in weird_indexes]
            print(textwrap.dedent(f"""

            Final dark pixels: avg: {np.mean(final_dark)}, sd: {np.std(final_dark)}
            Final usable pixels: avg: {np.mean(usable)}, sd: {np.std(usable)}
            """))

            try:
                input("Open the slit, press Enter.")
            except KeyboardInterrupt:
                sys.exit(1)

            # FIXME: now wavelength calibration


            sys.exit(1)

        min_exp, max_exp = argv.exposure
        exp, wavelengths, intensities = spd_with_auto_exposure(
                spectrometer, min_exp * 1000, max_exp * 1000,
                correct_nonlinearity=argv.correct_nonlinearity,
                correct_dark_counts=argv.correct_dark_counts)
        overexp = [k for (k,v) in zip(wavelengths, intensities) if v == spectrometer.max_intensity]
        match len(overexp):
            case 0:
                LOGGER.debug("Not overexposed.")
            case 1:
                LOGGER.debug('Over-exposed at %.3f', overexp[0])
            case _:
                LOGGER.debug('Over-exposed between %.3f and %.3f', min(overexp), max(overexp))

        w_new = np.arange(np.floor(wavelengths[0]), np.ceil(wavelengths[-1]) + 1)
        i_new = interp1d(wavelengths, intensities, kind='linear',
                         fill_value=(intensities[0], intensities[-1]),
                         bounds_error=False)(w_new)

        if argv.correct_above_zero:
            i_min = min(i_new)
            if i_min < 0:
                i_new = [x - i_min for x in i_new]

        if argv.max:
            i_corr = argv.max / max(i_new)
            i_new = [x * i_corr for x in i_new]

        LOGGER.debug("intensities: min: %.3f, max: %.3f", min(intensities), max(intensities))
        LOGGER.debug("i_new: min: %.3f, max: %.3f", min(i_new), max(i_new))

        snap_time = datetime.now()
        spectrum=Spectrum(
                status=ExposureStatus.OVER if len(overexp)>0 else ExposureStatus.NORMAL,
                exposure=ExposureMode.MANUAL if min_exp == max_exp else ExposureMode.AUTOMATIC,
                time=exp,
                spd=dict(zip([int(x) for x in w_new], i_new)),
                wavelength_range=range(int(min(w_new)), int(max(w_new))),
                wavelengths_raw=list(wavelengths),
                spd_raw=list(intensities),
                ts=snap_time,
                name=argv.name,
                device=spectrometer.model, # spectrometer.serial_number too?
                y_axis="counts"
        )

        template_values = {
                'name': argv.name or 'spectrum',
                'graph_type': '',
                'timestamp': str(int(snap_time.timestamp())),
                'timestamp_full': str(snap_time.timestamp()),
                'timestamp_human': str(snap_time),
        }
        filename = argv.file_template.format(**template_values) + '.json'
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(spectrum.to_json())
        print('Raw data saved as:', filename)

        if argv.plot:
            plt.plot(wavelengths, intensities, '-', label='Original data', color='blue')
            plt.plot(w_new, i_new, '-', label='Processed data', color='red')

            plt.xlabel('X')
            plt.ylabel('Y')
            plt.title('Interpolation of Data')
            plt.legend()
            plt.grid(True)

            plt.show()

    main()
    sys.exit(0)
