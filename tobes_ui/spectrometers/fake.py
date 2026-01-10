"""Class to pretend being a spectrometer, based on a JSON file"""

# pylint: disable=too-many-instance-attributes,too-many-locals,broad-exception-caught

import copy
from datetime import datetime
import pprint
import struct
import time

import numpy as np
from scipy.interpolate import interp1d

from tobes_ui.calibration.common import float_to_string
from tobes_ui.common import AttrDict
from tobes_ui.loader import Loader
import tobes_ui.loaders
from tobes_ui.logger import SUB_LOGGER
from tobes_ui.spectrometer import (BasicInfo, ExposureMode, ExposureStatus, Spectrometer,
                                   SpectrometerProperties, Spectrum)
from tobes_ui.properties import BoolProperty, EnumProperty, FloatProperty, IntProperty

LOGGER = SUB_LOGGER('fakespectrometer')


class FakeProperties(SpectrometerProperties):
    """Properties of the fake spectrometer (tweakable)"""
    exposure_mode = EnumProperty(ExposureMode)
    exposure_time = IntProperty(min_value=1, max_value=5000000) # needs adj @ runtime
    auto_max_exposure_time = IntProperty(min_value=1, max_value=5000000) # ditto
    auto_min_exposure_time = IntProperty(min_value=1, max_value=5000000) # ditto

    max_fps = FloatProperty(min_value=0, max_value=1000) # 0.5 is fine


class FakeSpectrometer(Spectrometer, registered_types = ['fake', 'fake-spectrometer']):
    """Pretends to be a spectrometer, using a single JSON as data source"""

    def __init__(self, path):
        if not path:
            raise ValueError("Need a path to json file to function")
        else:
            try:
                self._data = Loader.load('json:' + path)
            except (OSError, ValueError, json.decoder.JSONDecodeError) as exc:
                raise ValueError("Couldn't load json: {exc}") from exc

        self._consts = AttrDict()

        if 'constants' in self._data.meta:
            for k, v in self._data.meta['constants'].items():
                self._consts[k] = v

        if 'exposure_limits' in self._consts:
            exp_lim = self._consts.exposure_limits
        else:
            exp_lim = (1, 5000000)
        self._props = FakeProperties(
            exposure_mode=self._data.exposure,
            exposure_time=int(self._data.time),
            # auto_min_exposure_time, auto_max_exposure_time not set on purpose
            max_fps=0.5,
        )
        FakeProperties.exposure_time.min_value = exp_lim[0]
        FakeProperties.exposure_time.max_value = exp_lim[1]
        FakeProperties.auto_min_exposure_time.min_value = exp_lim[0]
        FakeProperties.auto_min_exposure_time.max_value = exp_lim[1]
        FakeProperties.auto_max_exposure_time.min_value = exp_lim[0]
        FakeProperties.auto_max_exposure_time.max_value = exp_lim[1]

        LOGGER.debug("Properties list: %s", self.properties_list())
        LOGGER.debug("Properties: %s", self.properties())
        LOGGER.debug("Constants: %s", self.constants())

        self._integration_time_set = None  # See _set_integration_time()

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
        pass

    @property
    def device_id(self):
        """Get device identifier (serial)"""
        return self._data.device

    @property
    def wavelength_range(self) -> range:
        """Get device spectral range (min, max) in nm"""
        return self._data.wavelength_range or self._consts.wavelength_range

    @property
    def exposure_mode(self):
        """Get device exposure mode"""
        return self._data.exposure

    @exposure_mode.setter
    def exposure_mode(self, mode: ExposureMode):
        """Set device exposure mode"""
        pass  # Can't really be set...

    @property
    def exposure_time(self):
        """Get device exposure time in microseconds"""
        return self._data.time

    @exposure_time.setter
    def exposure_time(self, exposure_time_us: int):
        """Set device exposure time in microseconds"""
        pass  # Can't really be set...

    @property
    def basic_info(self) -> BasicInfo:
        """Get basic info about the device"""
        return BasicInfo(
                device_type=self.__class__,
                device_id=self.device_id,
                wavelength_range=self.wavelength_range,
                exposure_mode=self.exposure_mode,
                time=self.exposure_time)

    def stream_data(self, where_to):
        """Stream spectral data to the where_to callback, until told to stop"""
        while True:
            spectrum=copy.deepcopy(self._data)
            spectrum.ts=datetime.now()

            if where_to:
                cont = where_to(spectrum)
                LOGGER.debug("callback says: %s", "continue" if cont else "stop")
                if not cont:
                    break
            else:
                print('Data (no where_to):')
                pprint.pprint(spectrum)

            max_fps = self._props.max_fps
            if max_fps <= 0:
                LOGGER.debug("freerun mode, overriding max_fps = 5")
                max_fps = 5
            sleepy_time = max(0, 1/max_fps)
            LOGGER.debug("thanks to max fps %.3f, sleeping for %.3fs", max_fps, sleepy_time)
            time.sleep(sleepy_time)

        LOGGER.debug("done")
        return self


    def supports_wavelength_calibration(self):
        """Introspection method to check whether the spectrometer supports WL calibration."""
        needed_constants = ['wavelength_calibration', 'dark_pixels', 'first_pixel', 'num_pixels']
        return all([c in self._consts for c in needed_constants])

    def read_wavelength_calibration(self):
        """Read WL calibration: [a3, a2, a1, a0] for polynomial a3*x^3 + a2*x^2 + a1*x + a0."""
        return self._consts.wavelength_calibration

    def write_wavelength_calibration(self, calibration):
        """Write WL calibration to eeprom."""
        LOGGER.info("Asked to write calibration: %s", calibration)
        return True
