"""Class to talk to Spectrometers"""

# pylint: disable=too-many-instance-attributes

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json

import colour

from tobes_ui.logger import LOGGER


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
        }, indent=4)

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
        return cls(
            status=data["status"],
            exposure=data["exposure"],
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
            device=data["device"]
        )

    @classmethod
    def from_file(cls, name: str) -> "Spectrum":
        """Load Spectrum from given file"""
        with open(name, 'r', encoding='utf-8') as file:
            return cls.from_json(file.read())


class Spectrometer(ABC):
    """Abstract base class for spectrometers."""
    _registry = []
    _spectrometer_types = {}

    @abstractmethod
    def get_basic_info(self) -> BasicInfo:
        """Get basic info about the device"""

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
