"""Class to talk to the Torch Bearer Spectrometer"""

from datetime import datetime
import json
import pprint
import struct
from typing import NamedTuple

import colour
from serial import Serial

from .protocol import (
    ExposureMode,
    ExposureStatus,
    MessageType,
    build_message,
    parse_messages
)


class Spectrum(NamedTuple):
    """Wraps measured spectrum"""
    status: ExposureStatus
    exposure: ExposureMode
    time: float
    spd: dict[int, float]
    wavelength_range: int
    spd_raw: list[float]
    ts: datetime

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
            "spd_raw": self.spd_raw,
            "ts": self.ts.timestamp(),
        }, indent=4)

    def to_spectral_distribution(self):
        """Convert Spectrum to colour.SpectralDistribution"""
        return colour.SpectralDistribution(self.spd, name=str(self.ts))

    @classmethod
    def from_json(cls, json_str: str) -> "Spectrum":
        """Convert json string to Spectrum"""
        data = json.loads(json_str)
        if "wavelength_range" not in data:
            wls = {int(k) for k,v in data["spd"].items()}
            data["wavelength_range"] = [min(wls), max(wls)]
        if "spd_raw" not in data:
            data["spd_raw"] = [v for k, v in data["spd"].items()]
        return cls(
            status=data["status"],
            exposure=data["exposure"],
            time=data["time"],
            spd={ int(k): v for k,v in data["spd"].items()},
            wavelength_range=range(
                data["wavelength_range"][0],
                data["wavelength_range"][1]
            ),
            spd_raw=data["spd_raw"],
            ts=datetime.fromtimestamp(data["ts"])
        )

    @classmethod
    def from_file(cls, name: str) -> "Spectrum":
        """Load Spectrum from given file"""
        with open(name, 'r', encoding='utf-8') as file:
            return cls.from_json(file.read())


class Spectrometer:
    """Handles the spectrometer (wraps the `protocol`)"""

    def __init__(self, path):
        try:
            self.port = Serial(path, 115200, timeout=0.1)
            self.buffer = b""
            self.wavelength_range = None
            self.exposure_mode = None
            self.device_id = None
        except Exception as ex:
            raise ValueError(f"Couldn't open serial: {ex}") from ex

    def send_message(self, message_type, data=b""):
        """Send message of given type and payload to the device"""
        if not self.port:
            raise ValueError("Already closed")

        self.port.write(build_message(message_type, data))

    def read_message(self, message_type=None):
        """Read message, possibly guarding the type"""
        if not self.port:
            raise ValueError("Already closed")

        while True:
            (self.buffer, messages) = parse_messages(self.buffer + self.port.read())

            if messages:
                message = messages[0]

                if message_type and message["message_type"] != message_type:
                    raise ValueError("Unexpected message type")

                return message

    def cleanup(self):
        """Cleanup function to ensure proper shutdown"""
        try:
            self.send_message(MessageType.STOP)
            self.port.close()
            self.port = None
            self.buffer = b""
            self.wavelength_range = None
        except Exception: # pylint: disable=broad-exception-caught
            pass  # Ignore errors during cleanup

    def get_device_id(self):
        """Get device identifier (serial)"""
        if not self.port:
            raise ValueError("Already closed")

        self.send_message(MessageType.GET_DEVICE_ID, b"\x18")
        response = self.read_message(MessageType.GET_DEVICE_ID)
        self.device_id = response['device_id']
        return response['device_id']

    def get_range(self) -> range:
        """Get device spectral range (min, max) in nm"""
        if not self.port:
            raise ValueError("Already closed")

        self.send_message(MessageType.GET_RANGE)
        response = self.read_message(MessageType.GET_RANGE)

        self.wavelength_range = range(
                response["start_wavelength"],
                response["end_wavelength"])

        return self.wavelength_range

    def set_exposure_mode(self, mode: ExposureMode):
        """Set device exposure mode"""
        if not self.port:
            raise ValueError("Already closed")

        self.send_message(MessageType.SET_EXPOSURE_MODE, struct.pack("<B", mode.value))
        response = self.read_message(MessageType.SET_EXPOSURE_MODE)
        if response['success']:
            self.exposure_mode = mode
        return response['success']

    def get_exposure_mode(self):
        """Get device exposure mode"""
        if not self.port:
            raise ValueError("Already closed")

        self.send_message(MessageType.GET_EXPOSURE_MODE)
        response = self.read_message(MessageType.GET_EXPOSURE_MODE)
        self.exposure_mode = response['exposure_mode']
        return response["exposure_mode"]

    def set_exposure_value(self, exposure_time_us: int):
        """Set device exposure mode in microseconds"""
        if not self.port:
            raise ValueError("Already closed")

        self.send_message(MessageType.SET_EXPOSURE_VALUE,
                          struct.pack("<I", exposure_time_us))
        response = self.read_message(MessageType.SET_EXPOSURE_VALUE)
        return response['success']

    def get_exposure_value(self):
        """Get device exposure mode in microseconds"""
        if not self.port:
            raise ValueError("Already closed")

        self.send_message(MessageType.GET_EXPOSURE_VALUE)
        response = self.read_message(MessageType.GET_EXPOSURE_VALUE)
        return response['exposure_time_us']

    def get_basic_info(self):
        """Get basic info about the device"""
        if not self.port:
            raise ValueError("Already closed")

        return {
                'device_id': self.get_device_id(),
                'range': self.get_range(),
                'exposure_mode': self.get_exposure_mode(),
                'exposure_value': self.get_exposure_value(),
                }

    def stream_data(self, where_to):
        """Stream spectral data to the where_to callback, until told to stop"""
        if not self.wavelength_range:
            spec_range = self.get_range()
        else:
            spec_range = self.wavelength_range

        if not self.exposure_mode:
            mode = self.get_exposure_mode()
            self.exposure_mode = mode

        self.send_message(MessageType.GET_DATA)

        while True:
            response = self.read_message()

            spectrum=Spectrum(
                    status=response['exposure_status'],
                    exposure=self.exposure_mode,
                    time=response["exposure_time"],
                    spd={
                        spec_range.start + index: value
                        for index, value in enumerate(response["spectrum"])
                    },
                    wavelength_range=spec_range,
                    spd_raw=response["spectrum"],
                    ts=datetime.now()
            )

            if where_to:
                cont = where_to(spectrum)
                if not cont:
                    break
            else:
                print('Data (no where_to):')
                pprint.pprint(spectrum)

        # Terminate streaming
        self.send_message(MessageType.STOP)
        while self.read_message()["message_type"] != MessageType.STOP:
            pass

        return self
