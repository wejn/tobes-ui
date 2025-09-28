"""Class to talk to the Ocean Optics Spectrometer"""

# pylint: disable=too-many-instance-attributes,too-many-locals,broad-exception-caught

from datetime import datetime
import pprint
import time

import numpy as np
from scipy.interpolate import interp1d
try:
    import seabreeze.spectrometers as sb
except ImportError as iex:
    raise ImportError("Missing ocean dependencies. "
                      "Install them via: pip/pipx install tobes-ui[ocean]") from iex

from tobes_ui.logger import LOGGER
from tobes_ui.spectrometer import BasicInfo, ExposureMode, ExposureStatus, Spectrometer, Spectrum


class OceanOpticsSpectrometer(Spectrometer, registered_types = ['oo', 'ocean', 'oceanoptics']):
    """Handles the Ocean Optics Spectrometers via pyseabreeze"""

    def __init__(self, path):
        try:
            if not path:
                self._spectrometer = sb.Spectrometer.from_first_available()
            else:
                self._spectrometer = sb.Spectrometer.from_serial_number(path)
        except Exception as ex:
            LOGGER.debug("exception", exc_info=True)
            try:
                available = sb.list_devices()
            except Exception:
                available = None

            raise ValueError(f"Couldn't initialize spectrometer({path}): {ex}"
                             f" (available: {available})") from ex

        if self._spectrometer.serial_number.startswith("FLMS"):
            # According to docs: 0-17 optical black, 18-19 not usable, 20-2047 active
            self._dark_pixels = list(range(6,19))  # 6..18, absent of better cali
            self._first_pixel = 20
        else:
            LOGGER.warning("This spectrometer model (%s) was not tested first hand.",
                           self._spectrometer.serial_number)
            self._dark_pixels = self._spectrometer._dp
            self._first_pixel = max(self._spectrometer._dp) + 1

        LOGGER.debug("Dark pixels: %s, first pixel: %s", self._dark_pixels, self._first_pixel)

        self._nonlinearity_coeffs = None
        nc_feature = self._spectrometer.f.nonlinearity_coefficients
        if nc_feature:
            try:
                self._nonlinearity_coeffs = np.poly1d(
                        nc_feature.get_nonlinearity_coefficients()[::-1])
            except sb.SeaBreezeError:
                pass
        if self._nonlinearity_coeffs:
            LOGGER.debug("Non-linearity coeffs: %s", self._nonlinearity_coeffs.coefficients)
        else:
            LOGGER.debug("No non-linearity coeffs available.")

        feats = [k for k, v in self._spectrometer.features.items() if v]
        LOGGER.debug("Initialized %s with %s", self._spectrometer, feats)

        wls = self._spectrometer.wavelengths()
        min_wl = int(np.floor(wls[self._first_pixel]))
        max_wl = int(np.ceil(wls[-1]))
        self._wavelength_range = range(min_wl, max_wl)
        LOGGER.debug("Wavelength range: %s", self._wavelength_range)

        self._max_intensity = self._spectrometer.max_intensity
        LOGGER.debug("Max intensity: %s", self._max_intensity)

        # FIXME: these should be configurable properties
        self._exposure_mode = ExposureMode.AUTOMATIC
        self._exposure_limits = self._spectrometer.integration_time_micros_limits
        self._exposure_time = 128000
        self._correct_dark_counts = True
        self._correct_nonlinearity = False
        self._max_fps = 0.8  # FIXME: this is a travesty, but one we must suffer for now
        self._auto_max_threshold = 0.9  # max threshold in auto exposure mode

    def cleanup(self):
        """Cleanup function to ensure proper shutdown"""
        try:
            if self._spectrometer:
                LOGGER.debug("cleaning up")
                self._spectrometer.close()
                self._spectrometer = None
        except Exception: # pylint: disable=broad-exception-caught
            LOGGER.debug("exception", exc_info=True)

    @property
    def device_id(self):
        """Get device identifier (serial)"""
        if not self._spectrometer:
            raise ValueError("Not active")

        return f"{self._spectrometer.model} {self._spectrometer.serial_number}"

    @property
    def wavelength_range(self) -> range:
        """Get device spectral range (min, max) in nm"""
        if not self._spectrometer:
            raise ValueError("Not active")

        return self._wavelength_range

    @property
    def exposure_mode(self):
        """Get device exposure mode"""
        if not self._spectrometer:
            raise ValueError("Not active")

        return self._exposure_mode

    @exposure_mode.setter
    def exposure_mode(self, mode: ExposureMode):
        """Set device exposure mode"""
        if not self._spectrometer:
            raise ValueError("Not active")

        self._exposure_mode = mode

    @property
    def exposure_time(self):
        """Get device exposure time in microseconds"""
        if not self._spectrometer:
            raise ValueError("Not active")

        return self._exposure_time

    @exposure_time.setter
    def exposure_time(self, exposure_time_us: int):
        """Set device exposure time in microseconds"""
        if not self._spectrometer:
            raise ValueError("Not active")

        if not self._exposure_limits[0] <= exposure_time_us <= self._exposure_limits[1]:
            raise ValueError(f"Requested time {exposure_time_us} outside {self._exposure_limits}")

        self._exposure_time = exposure_time_us

    @property
    def basic_info(self) -> BasicInfo:
        """Get basic info about the device"""
        if not self._spectrometer:
            raise ValueError("Not active")

        return BasicInfo(
                device_type=self.__class__,
                device_id=self.device_id,
                wavelength_range=self.wavelength_range,
                exposure_mode=self.exposure_mode,
                time=self.exposure_time)

    def _spd_with_auto(self, init_time, min_time=None, max_time=None, min_step=1000):
        """Get spectral distribution in auto exposure mode (within limits)"""
        hw_min, hw_max = self._spectrometer.integration_time_micros_limits
        if not min_time or min_time < hw_min:
            low = hw_min
        else:
            low = min_time
        if not max_time or max_time > hw_max:
            high = hw_max
        else:
            high = max_time

        data = None
        initial = True

        def is_overexposed(intensities):
            return len([1 for v in intensities
                        if v > self._max_intensity * self._auto_max_threshold]) > 0

        while initial or high - low > min_step:
            mid = init_time if initial else (low + high) / 2.0
            self._spectrometer.integration_time_micros(mid)
            wls, i = self._spectrometer.spectrum()  # see stream_data() as to why like this
            data = [wls, i]

            if is_overexposed(i):
                LOGGER.debug("Over-exposed at %dµs", int(mid))
                high = mid  # Too bright, decrease time
                initial = False
            else:
                LOGGER.debug("Good exposure at %dµs", int(mid))
                low = mid
                if initial:
                    break
                initial = False

        if not initial:
            LOGGER.debug("Final exposure at %dµs", int(mid))
        return int(mid), *data

    def stream_data(self, where_to):
        """Stream spectral data to the where_to callback, until told to stop"""
        if not self._spectrometer:
            raise ValueError("Not active")

        LOGGER.debug("enter")
        while True:
            mode = self.exposure_mode
            LOGGER.debug("Getting spectrum...")
            if mode == ExposureMode.AUTOMATIC:
                exp_time, wavelengths, intensities = self._spd_with_auto(self.exposure_time)
                self.exposure_time = exp_time  # in auto mode, remember the exposure time
            else:
                self._spectrometer.integration_time_micros(self.exposure_time)
                wavelengths, intensities = self._spectrometer.spectrum()
                exp_time = self.exposure_time

            # Not correcting DC directly in the call to `spectrum` in `spd_with_auto_exposure`
            # for two reasons:
            # 1. We're using different dark pixels (self._dark_pixels)
            # 2. With the correction on, detecting over-exposure is impossible

            not_used_pixels = intensities[:self._first_pixel]  # FIXME: maybe include in extra data?
            wavelengths = wavelengths[self._first_pixel:]
            intensities = intensities[self._first_pixel:]

            overexp = [k for (k,v) in zip(wavelengths, intensities) if v == self._max_intensity]

            dark_mean = np.mean(not_used_pixels[self._dark_pixels])
            LOGGER.debug('dark_mean(%d px): %.3f', len(self._dark_pixels), dark_mean)

            # Correcting dark counts and non-linearity
            match (self._correct_dark_counts, self._correct_nonlinearity):
                case (False, False):
                    pass
                case (True, False):
                    intensities = np.maximum(intensities - dark_mean, 0.0)
                case (False, True):
                    if self._nonlinearity_coeffs:
                        new_int = intensities - dark_mean
                        new_int /= np.polyval(self._nonlinearity_coeffs, new_int)
                        intensities = new_int + dark_mean
                case (True, True):
                    intensities = np.maximum(intensities - dark_mean, 0.0)
                    if self._nonlinearity_coeffs:
                        intensities /= np.polyval(self._nonlinearity_coeffs, intensities)

            # Interpolating to whole numbers
            w_new = np.arange(np.floor(wavelengths[0]), np.ceil(wavelengths[-1]) + 1)
            i_new = interp1d(wavelengths, intensities, kind='linear',
                             fill_value=(intensities[0], intensities[-1]),
                             bounds_error=False)(w_new)

            match len(overexp):
                case 0:
                    LOGGER.debug("Not overexposed, intensities: (%.3f, %.3f).",
                                 min(i_new), max(i_new))
                case 1:
                    LOGGER.debug('Over-exposed at %.3f, intensities: (%.3f, %.3f).',
                                 overexp[0], min(i_new), max(i_new))
                case _:
                    LOGGER.debug('Over-exposed (%.3f, %.3f), intensities: (%.3f, %.3f).',
                                 min(overexp), max(overexp), min(i_new), max(i_new))

            spectrum=Spectrum(
                    status=ExposureStatus.OVER if len(overexp)>0 else ExposureStatus.NORMAL,
                    exposure=mode,
                    time=exp_time / 1000,  # to ms
                    spd=dict(zip([int(x) for x in w_new], i_new)),
                    wavelength_range=self.wavelength_range,
                    wavelengths_raw=list(wavelengths),
                    spd_raw=list(intensities),
                    ts=datetime.now(),
                    name=None,
                    device=self.device_id,
                    y_axis="counts"
            )

            if where_to:
                cont = where_to(spectrum)
                LOGGER.debug("callback says: %s", "continue" if cont else "stop")
                if not cont:
                    break
            else:
                print('Data (no where_to):')
                pprint.pprint(spectrum)

            if self._max_fps > 0:
                interval = 1 / self._max_fps
                sleepy_time = max(0, interval - exp_time/1000000)
                LOGGER.debug("thanks to max fps %.3f, sleeping for %.3fs",
                             self._max_fps, sleepy_time)
                time.sleep(sleepy_time)

        LOGGER.debug("done")
        return self
