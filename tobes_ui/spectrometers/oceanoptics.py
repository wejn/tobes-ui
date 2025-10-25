"""Class to talk to the Ocean Optics Spectrometer"""

# pylint: disable=too-many-instance-attributes,too-many-locals,broad-exception-caught

import copy
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

from tobes_ui.common import AttrDict
from tobes_ui.logger import SUB_LOGGER
from tobes_ui.spectrometer import (BasicInfo, ExposureMode, ExposureStatus, Spectrometer,
                                   SpectrometerProperties, Spectrum)
from tobes_ui.properties import BoolProperty, EnumProperty, FloatProperty, IntProperty

LOGGER = SUB_LOGGER('oceanoptics')


class OceanOpticsProperties(SpectrometerProperties):
    """Properties of the OO spectrometer (tweakable)"""
    exposure_mode = EnumProperty(ExposureMode)
    exposure_time = IntProperty(min_value=1, max_value=5000000) # needs adj @ runtime
    auto_max_exposure_time = IntProperty(min_value=1, max_value=5000000) # ditto
    auto_min_exposure_time = IntProperty(min_value=1, max_value=5000000) # ditto
    auto_min_step = IntProperty(min_value=1, max_value=10000) # defaults to 1k

    correct_dark_counts = BoolProperty()
    correct_nonlinearity = BoolProperty()
    max_fps = FloatProperty(min_value=0, max_value=1000) # 0.8 is fine
    auto_max_threshold = FloatProperty(min_value=0.1, max_value=0.999) # 0.9 is fine


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

        self._consts = AttrDict()

        if self._spectrometer.serial_number.startswith("FLMS"):
            # According to docs: 0-17 optical black, 18-19 not usable, 20-2047 active
            dark_pixels = list(range(6,19))  # 6..18, absent of better cali
            first_pixel = 20
        else:
            LOGGER.warning("This spectrometer model (%s) was not tested first hand.",
                           self._spectrometer.serial_number)
            dark_pixels = self._spectrometer._dp
            first_pixel = max(self._spectrometer._dp) + 1

        self._consts.update({
            'dark_pixels': dark_pixels,
            'first_pixel': first_pixel,
        })

        self._consts.nonlinearity_coeffs = None
        nc_feature = self._spectrometer.f.nonlinearity_coefficients
        if nc_feature:
            try:
                self._consts.nonlinearity_coeffs = np.poly1d(
                        nc_feature.get_nonlinearity_coefficients()[::-1])
            except sb.SeaBreezeError:
                pass

        self._consts.features = [k for k, v in self._spectrometer.features.items() if v]
        LOGGER.debug("Initialized %s with %s", self._spectrometer, self._consts.features)

        wls = self._spectrometer.wavelengths()
        min_wl = int(np.floor(wls[self._consts.first_pixel]))
        max_wl = int(np.ceil(wls[-1]))
        self._consts.wavelength_range = range(min_wl, max_wl)

        self._consts.max_intensity = self._spectrometer.max_intensity

        exp_lim = self._spectrometer.integration_time_micros_limits
        self._consts.exposure_limits = exp_lim

        self._props = OceanOpticsProperties(
            exposure_mode=ExposureMode.AUTOMATIC,
            exposure_time=128000,
            # auto_min_step, auto_min_exposure_time, auto_max_exposure_time not set on purpose
            correct_dark_counts=True,
            correct_nonlinearity=False,
            max_fps=0.8,
            auto_max_threshold=0.9
        )
        OceanOpticsProperties.exposure_time.min_value = exp_lim[0]
        OceanOpticsProperties.exposure_time.max_value = exp_lim[1]
        OceanOpticsProperties.auto_min_exposure_time.min_value = exp_lim[0]
        OceanOpticsProperties.auto_min_exposure_time.max_value = exp_lim[1]
        OceanOpticsProperties.auto_max_exposure_time.min_value = exp_lim[0]
        OceanOpticsProperties.auto_max_exposure_time.max_value = exp_lim[1]

        LOGGER.debug("Properties list: %s", self.properties_list())
        LOGGER.debug("Properties: %s", self.properties())
        LOGGER.debug("Constants: %s", self.constants())

    def constants(self):
        """Return list of spectrometer-related constants with their values"""
        return copy.deepcopy(self._consts)

    def properties_list(self):
        """Return list of configurable properties"""
        return self._props.properties()

    def property_get(self, name):
        """Get value of property with given name"""
        return self._props.get(name)

    def property_set(self, name, value):
        """Set property of given name to value"""
        LOGGER.debug("%s -> %s", name, value)
        self._props.set(name, value)

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

        return self._consts.wavelength_range

    @property
    def exposure_mode(self):
        """Get device exposure mode"""
        if not self._spectrometer:
            raise ValueError("Not active")

        return self._props.exposure_mode

    @exposure_mode.setter
    def exposure_mode(self, mode: ExposureMode):
        """Set device exposure mode"""
        if not self._spectrometer:
            raise ValueError("Not active")

        self._props.exposure_mode = mode

    @property
    def exposure_time(self):
        """Get device exposure time in microseconds"""
        if not self._spectrometer:
            raise ValueError("Not active")

        return self._props.exposure_time

    @exposure_time.setter
    def exposure_time(self, exposure_time_us: int):
        """Set device exposure time in microseconds"""
        if not self._spectrometer:
            raise ValueError("Not active")

        self._props.exposure_time = exposure_time_us

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

    def _spd_with_auto(self, init_time):
        """Get spectral distribution in auto exposure mode (within limits)"""
        low, high = self._spectrometer.integration_time_micros_limits

        min_step = self._props.auto_min_step
        min_time = self._props.auto_min_exposure_time
        max_time = self._props.auto_max_exposure_time

        # d'oh
        if min_time and max_time and min_time > max_time:
            min_time, max_time = max_time, min_time

        # cap low/high at hw limits
        if min_time:
            low = max(low, min_time)
        if max_time:
            high = min(high, max_time)

        # cap init within low..high
        init_time = max(low, min(high, init_time))

        if not min_step:
            min_step = (high - low) / (2 ** 4) # at most ~4 iterations
            LOGGER.debug("Chose min_step: %.2f", min_step)

        data = None
        initial = True

        def is_overexposed(intensities):
            return len([1 for v in intensities
                        if v > self._consts.max_intensity * self._props.auto_max_threshold]) > 0

        while initial or high - low > min_step:
            mid = init_time if initial else (low + high) / 2.0
            self._spectrometer.integration_time_micros(mid)
            wls, i = self._spectrometer.spectrum()  # see stream_data() as to why like this
            data = [wls, i]

            if is_overexposed(i[self._consts.first_pixel:]): # only consider live pixels...
                LOGGER.debug("Over-exposed at %dµs", int(mid))
                high = mid  # Too bright, decrease time
                initial = False
            else:
                current_max_int = max(i[self._consts.first_pixel:])
                LOGGER.debug("Good exposure at %dµs (%.3f%% of max)", int(mid),
                             100*(current_max_int/self._consts.max_intensity))
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
            # 1. We're using different dark pixels (self._consts.dark_pixels)
            # 2. With the correction on, detecting over-exposure is impossible

            not_used_pixels = intensities[:self._consts.first_pixel]
            wavelengths = wavelengths[self._consts.first_pixel:]
            intensities = intensities[self._consts.first_pixel:]

            overexp = [k for (k,v) in zip(wavelengths, intensities)
                       if v == self._consts.max_intensity]

            dark_mean = np.mean(not_used_pixels[self._consts.dark_pixels])
            LOGGER.debug('dark_mean(%d px): %.3f', len(self._consts.dark_pixels), dark_mean)

            # Correcting dark counts and non-linearity
            match (self._props.correct_dark_counts, self._props.correct_nonlinearity):
                case (False, False):
                    pass
                case (True, False):
                    intensities = np.maximum(intensities - dark_mean, 0.0)
                case (False, True):
                    if self._consts.nonlinearity_coeffs:
                        new_int = intensities - dark_mean
                        new_int /= np.polyval(self._consts.nonlinearity_coeffs, new_int)
                        intensities = new_int + dark_mean
                case (True, True):
                    intensities = np.maximum(intensities - dark_mean, 0.0)
                    if self._consts.nonlinearity_coeffs:
                        intensities /= np.polyval(self._consts.nonlinearity_coeffs, intensities)

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

            max_fps = self._props.max_fps
            if max_fps > 0:
                sleepy_time = max(0, 1/max_fps - exp_time/1000000)
                LOGGER.debug("thanks to max fps %.3f, sleeping for %.3fs", max_fps, sleepy_time)
                time.sleep(sleepy_time)

        LOGGER.debug("done")
        return self


    def supports_wavelength_calibration(self):
        """Introspection method to check whether the spectrometer supports WL calibration."""
        return True

    def read_wavelength_calibration(self):
        """Read WL calibration: [a3, a2, a1, a0] for polynomial a3*x^3 + a2*x^2 + a1*x + a0."""
        coeffs = []
        eeprom = self._spectrometer.f.eeprom
        # Slots 1-4 are wavelength calibration
        for i in range(1, 5):
            try:
                # For some reason this can be empty
                coeffs.append(float(eeprom.eeprom_read_slot(i).split(b'\x00')[0]))
            except (ValueError, IndexError):
                coeffs.append(0.0)
        # a0, a1, a2, a3 -> a3, a2, a1, a0
        return coeffs[::-1]
