"""Class to talk to the Torch Bearer Spectrometer"""

# pylint: disable=too-many-instance-attributes

from dataclasses import dataclass
from datetime import datetime
import json
import pprint
import struct

import colour
from serial import Serial

from .logger import LOGGER
from .protocol import (
    ExposureMode,
    ExposureStatus,
    MessageType,
    build_message,
    parse_messages
)


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
            LOGGER.debug("exception", exc_info=True)
            raise ValueError(f"Couldn't open serial: {ex}") from ex

    def send_message(self, message_type, data=b""):
        """Send message of given type and payload to the device"""
        if not self.port:
            raise ValueError("Already closed")

        LOGGER.debug("sending %s %s", message_type, data)
        self.port.write(build_message(message_type, data))

    def read_message(self, message_type=None):
        """Read message, possibly guarding the type"""
        if not self.port:
            raise ValueError("Already closed")

        while True:
            (self.buffer, messages) = parse_messages(self.buffer + self.port.read(), 1)

            if messages:
                message = messages[0]

                LOGGER.debug("received type %s, want %s", message["message_type"], message_type)

                if message_type and message["message_type"] != message_type:
                    LOGGER.debug("throwing exc")
                    raise ValueError("Unexpected message type")

                LOGGER.debug("returning %s", message["message_type"])
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
            LOGGER.debug("exception", exc_info=True)

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
        LOGGER.debug("enter")
        if not self.wavelength_range:
            spec_range = self.get_range()
        else:
            spec_range = self.wavelength_range

        if not self.exposure_mode:
            mode = self.get_exposure_mode()
        else:
            mode = self.exposure_mode

        if not self.device_id:
            device_id = self.get_device_id()
        else:
            device_id = self.device_id
        device = device_id.split('-')[0]

        LOGGER.debug("requesting data")
        self.send_message(MessageType.GET_DATA)

        last_ok = False
        while True:
            LOGGER.debug("reading")
            response = self.read_message()
            LOGGER.debug("read %s", response)

            if response['message_type'] != MessageType.GET_DATA:
                if response['message_type'] == MessageType.STOP:
                    # FIXME: rootcause this, and don't quickfix
                    LOGGER.info('quickfixing stall (STOP rcvd in get_data)')
                    self.send_message(MessageType.GET_DATA)
                    continue
                LOGGER.info('unexpected message: %s', response)
                continue

            last_ok = response['exposure_status'] == ExposureStatus.NORMAL

            spectrum=Spectrum(
                    status=response['exposure_status'],
                    exposure=mode,
                    time=response["exposure_time"],
                    spd={
                        spec_range.start + index: value
                        for index, value in enumerate(response["spectrum"])
                    },
                    wavelength_range=spec_range,
                    wavelengths_raw=list(range(spec_range.start, spec_range.stop + 1)),
                    spd_raw=response["spectrum"],
                    ts=datetime.now(),
                    name=None,
                    device=device,
                    y_axis="$W\\cdot{}m^{-2}\\cdot{}nm^{-1}$"
            )

            if where_to:
                cont = where_to(spectrum)
                LOGGER.debug("callback says: %s", "continue" if cont else "stop")
                if not cont:
                    break
            else:
                print('Data (no where_to):')
                pprint.pprint(spectrum)

        # Terminate streaming
        LOGGER.debug("about to stop %s", last_ok)
        self.send_message(MessageType.STOP)
        if last_ok:
            while (msg := self.read_message()["message_type"]) != MessageType.STOP:
                LOGGER.debug("wait-stop msg %s", msg)
        else:
            # When the last GET_DATA message wasn't OK, the system doesn't send
            # ACK to the STOP message.
            pass

        LOGGER.debug("done")
        return self
