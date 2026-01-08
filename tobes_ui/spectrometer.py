"""Class to talk to Spectrometers"""

# pylint: disable=too-many-instance-attributes

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json

import colour
import numpy as np

from tobes_ui.logger import LOGGER
from tobes_ui.properties import PropertyContainer


@dataclass
class BasicInfo:
    """Basic spectrometer info"""
    device_type: 'Spectrometer'
    device_id: str
    wavelength_range: range
    exposure_mode: 'ExposureMode'
    time: float


class ExposureMode(Enum):
    """Type of exposure mode"""
    MANUAL = 0x00
    AUTOMATIC = 0x01

    def __str__(self):
        """Convert to readable string"""
        return str(self.name).lower()


class ExposureStatus(Enum):
    """Status of exposure"""
    NORMAL = 0x00
    OVER = 0x01
    UNDER = 0x02

    def __str__(self):
        """Convert to readable string"""
        return str(self.name).lower()


class SpectrumEncoder(json.JSONEncoder):
    """Custom encoder to serialize various classes in meta"""
    def default(self, o):
        if isinstance(o, np.poly1d):
            return o.coefficients.tolist()
        if isinstance(o, range):
            return (o.start, o.stop)
        if isinstance(o, ExposureMode):
            return str(o)
        if isinstance(o, ExposureStatus):
            return str(o)
        return super().default(o)


@dataclass
class Spectrum:
    """Wraps measured spectrum"""
    status: ExposureStatus
    exposure: ExposureMode
    time: float
    spd: dict[int, float]
    wavelength_range: range
    wavelengths_raw: list[float]
    spd_raw: list[float]
    ts: datetime # pylint: disable=invalid-name
    name: str
    y_axis: str
    device: str
    meta: dict[str, any]

    REQUIRED_KEYS = [
            'status',
            'exposure',
            'time',
            'spd',
            'ts',
    ]

    def to_json(self) -> str:
        """Convert Spectrum to json"""
        return json.dumps({
            "status": str(self.status),
            "exposure": str(self.exposure),
            "time": self.time,
            "spd": self.spd,
            "wavelength_range": [
                self.wavelength_range.start,
                self.wavelength_range.stop
            ],
            "wavelengths_raw": self.wavelengths_raw,
            "spd_raw": self.spd_raw,
            "ts": self.ts.timestamp(),
            "name": self.name,
            "y_axis": self.y_axis,
            "device": self.device,
            "meta": self.meta,
        }, indent=4, cls=SpectrumEncoder)

    def to_spectral_distribution(self):
        """Convert Spectrum to colour.SpectralDistribution"""
        return colour.SpectralDistribution(self.spd, name=str(self.ts))

    @classmethod
    def from_json(cls, json_str: str) -> "Spectrum":
        """Convert json string to Spectrum"""
        data = json.loads(json_str)
        if not set(cls.REQUIRED_KEYS).issubset(set(data.keys())):
            raise ValueError('missing some required keys,' +
                             f' want: {set(cls.REQUIRED_KEYS)},' +
                             f' have: {set(data.keys())}')
        if "wavelength_range" not in data:
            wls = {int(k) for k,v in data["spd"].items()}
            data["wavelength_range"] = [min(wls), max(wls)]
        if "wavelengths_raw" not in data:
            data["wavelengths_raw"] = [k for k, v in data["spd"].items()]
        if "spd_raw" not in data:
            data["spd_raw"] = [v for k, v in data["spd"].items()]
        if "name" not in data:
            data["name"] = None
        if "y_axis" not in data:
            data["y_axis"] = 'counts'
        if "device" not in data:
            data["device"] = None
        if "meta" not in data:
            data["meta"] = {}
        return cls(
            status=ExposureStatus[data["status"].upper()],
            exposure=ExposureMode[data["exposure"].upper()],
            time=data["time"],
            spd={ int(k): v for k,v in data["spd"].items()},
            wavelength_range=range(
                data["wavelength_range"][0],
                data["wavelength_range"][1]
            ),
            wavelengths_raw=data["wavelengths_raw"],
            spd_raw=data["spd_raw"],
            ts=datetime.fromtimestamp(data["ts"]),
            name=data["name"],
            y_axis=data["y_axis"],
            device=data["device"],
            meta=data["meta"],
        )

    @classmethod
    def from_file(cls, name: str) -> "Spectrum":
        """Load Spectrum from given file"""
        with open(name, 'r', encoding='utf-8') as file:
            return cls.from_json(file.read())


class SpectrometerProperties(PropertyContainer):
    """Properties common to all spectrometers."""
    # None at the moment


class Spectrometer(ABC):
    """Abstract base class for spectrometers."""
    _registry = []
    _spectrometer_types = {}

    @property
    @abstractmethod
    def basic_info(self) -> BasicInfo:
        """Get basic info about the device"""

    @property
    @abstractmethod
    def exposure_mode(self):
        """Get device exposure mode"""

    @exposure_mode.setter
    @abstractmethod
    def exposure_mode(self, mode: ExposureMode):
        """Set device exposure mode"""

    @property
    @abstractmethod
    def exposure_time(self):
        """Get device exposure time in microseconds"""

    @exposure_time.setter
    @abstractmethod
    def exposure_time(self, exposure_time_us: int):
        """Set device exposure time in microseconds"""

    @abstractmethod
    def stream_data(self, where_to):
        """Stream spectral data to the where_to callback, until told to stop"""

    @abstractmethod
    def cleanup(self):
        """Cleanup function to ensure proper shutdown"""

    def __init_subclass__(cls, registered_types: list[str] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        Spectrometer._registry.append(cls)
        for type_ in registered_types or []:
            Spectrometer._spectrometer_types[type_] = cls

    @classmethod
    def spectrometer_types(cls):
        """Return registered spectrometer types"""
        return list(cls._spectrometer_types.keys())

    @classmethod
    def create(cls, input_device: str) -> 'Spectrometer':
        """Factory method for Spectrometers"""
        import tobes_ui.spectrometers  # pylint: disable=import-outside-toplevel, unused-import

        if ':' in input_device:
            type_, spec_id = input_device.split(':', 2)

            if type_ in Spectrometer._spectrometer_types:
                LOGGER.debug("Trying spectrometer type=%s with id=%s", type_, spec_id)
                try:
                    spec = Spectrometer._spectrometer_types[type_](spec_id)
                    LOGGER.debug("Success: %s", spec)
                    return spec
                except Exception as ex:  # pylint: disable=broad-exception-caught
                    LOGGER.debug("Spectrometer type=%s doesn't work: %s", type_, ex)
                    raise ValueError(f"Couldn't initialize spectrometer {type_}: {ex})") from ex

            raise ValueError(f'No such spectrometer type: {type_}')

        LOGGER.debug("Brute-forcing spectrometers for %s", input_device)
        # Brute force
        for spec_cls in Spectrometer._registry:
            LOGGER.debug("Trying spectrometer class: %s", spec_cls)
            try:
                spec = spec_cls(input_device)
                LOGGER.debug("Success: %s", spec)
                return spec
            except Exception as ex:  # pylint: disable=broad-exception-caught
                LOGGER.debug("Spectrometer type=%s doesn't work: %s", spec_cls, ex)

        raise ValueError(f'No spectrometer implementation can take {input_device} as input')

    def supports_wavelength_calibration(self):
        """Introspection method to check whether the spectrometer supports WL calibration."""
        return False

    def read_wavelength_calibration(self):
        """Optional hook method for reading WL calibration (if supported)."""
        raise NotImplementedError("This is by default not supported; override if needed")

    def write_wavelength_calibration(self, calibration):
        """Optional hook method for writing WL calibration (if supported)."""
        raise NotImplementedError("This is by default not supported; override if needed")

    @abstractmethod
    def properties_list(self):
        """Return list of configurable properties.

        You MUST use subclass of SpectrometerProperties for your properties,
        and this method should call properties() on its instance.
        """

    @abstractmethod
    def property_get(self, name):
        """Get value of property with given name.

        You MUST use subclass of SpectrometerProperties for your properties,
        and this method should call get() on its instance.
        """

    @abstractmethod
    def property_set(self, name, value):
        """Set property of given name to value.

        You MUST use subclass of SpectrometerProperties for your properties,
        and this method should call set() on its instance.
        """

    def properties(self):
        """Return list of properties with their values"""
        return {item['name']: self.property_get(item['name']) for item in self.properties_list()}

    def properties_set_many(self, props):
        """Set many properties in a single call using name:value hash"""
        for name, value in props.items():
            self.property_set(name, value)

    def constants(self):
        """Return list of spectrometer-related constants with their values. Optional.

        This is useful to return integration limits and various other internals.
        It is not expected that these are truly constants (they can change between calls),
        but they are not expected to be modified by the user -- the way properties are.
        """
        return {}  # By default: no constants
