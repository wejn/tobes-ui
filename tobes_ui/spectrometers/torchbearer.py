"""Class to talk to the Torch Bearer Spectrometer"""

# pylint: disable=too-many-instance-attributes

from datetime import datetime
from enum import Enum
import pprint
import struct

from serial import Serial

from tobes_ui.logger import LOGGER
from tobes_ui.spectrometer import BasicInfo, ExposureMode, ExposureStatus, Spectrometer, Spectrum

class TBExposureMode(Enum):
    """Type of exposure mode"""
    MANUAL = 0x00
    AUTOMATIC = 0x01


class TBExposureStatus(Enum):
    """Status of exposure"""
    NORMAL = 0x00
    OVER = 0x01
    UNDER = 0x02


class MessageType(Enum):
    """Type of message (command) sent or received"""
    STOP = 0x04
    GET_DEVICE_ID = 0x08
    SET_EXPOSURE_MODE = 0x0A
    GET_EXPOSURE_MODE = 0x0B
    SET_EXPOSURE_VALUE = 0x0C
    GET_EXPOSURE_VALUE = 0x0D
    GET_RANGE = 0x0F
    GET_DATA = 0x33

    def __str__(self):
        """Convert to readable string"""
        return str(self.name).lower()


class TorchBearerSpectrometer(Spectrometer, registered_types = ['tb', 'torchbearer']):
    """Handles the Torch Bearer Spectrometer"""

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
        self.port.write(self._build_message(message_type, data))

    def read_message(self, message_type=None):
        """Read message, possibly guarding the type"""
        if not self.port:
            raise ValueError("Already closed")

        while True:
            (self.buffer, messages) = self._parse_messages(self.buffer + self.port.read(), 1)

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

    def get_basic_info(self) -> BasicInfo:
        """Get basic info about the device"""
        if not self.port:
            raise ValueError("Already closed")

        return BasicInfo(
                device_type=self.__class__,
                device_id=self.get_device_id(),
                wavelength_range=self.get_range(),
                exposure_mode=self.get_exposure_mode(),
                time=self.get_exposure_value())

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

    def _decode_spectrum(self, encoded_spectrum, encoded_exponent, exposure_time, serial, ex_info):
        exposure_time_bytes = struct.pack("<f", exposure_time)
        exposure_time = int.from_bytes(exposure_time_bytes, "little")

        common = int.from_bytes(exposure_time_bytes, "big") ^ ex_info >> 16
        key_a = (common ^ (exposure_time ^ serial) >> 16 ^ serial ^ ex_info) & 0xFFFF
        key_b = (common >> 16 ^ exposure_time ^ serial) & 0xFFFF

        exponent = struct.unpack(">H", struct.pack("<H", encoded_exponent))[0] ^ 8848
        scale = pow(10, exponent)

        midpoint = len(encoded_spectrum) // 2

        return [
            (item ^ (key_a if index < midpoint else key_b)) / scale
            for index, item in enumerate(encoded_spectrum)
        ]

    def _calculate_checksum(self, message):
        return sum(message) & 0xFF


    def _build_message(self, message_type, data):
        """Build message of given type with data as payload"""
        LOGGER.debug('%s %s', message_type, data)
        message = b"\xCC\x01"
        message += int.to_bytes(9 + len(data), 3, "little")
        message += int.to_bytes(message_type.value, 1, "little")
        message += data
        message += int.to_bytes(self._calculate_checksum(message), 1, "little")
        message += b"\x0D\x0A"

        return message


    def _parse_message(self, message_type, data):
        message = {"message_type": message_type}

        match message_type:
            case MessageType.GET_DEVICE_ID:
                message["device_id"] = data.decode("ascii")

            case MessageType.SET_EXPOSURE_MODE:
                if len(data) == 1:
                    message["success"] = data[0] == 0x00
                else:
                    message["exposure_mode"] = ExposureMode(data[0])

            case MessageType.GET_EXPOSURE_MODE:
                message["exposure_mode"] = ExposureMode(data[0])

            case MessageType.SET_EXPOSURE_VALUE:
                message["success"] = data[0] == 0x00

            case MessageType.GET_EXPOSURE_VALUE:
                message["exposure_time_us"] = struct.unpack("<I", data)[0]

            case MessageType.GET_RANGE:
                message["start_wavelength"], message["end_wavelength"] = struct.unpack(
                    "<HH", data
                )

            case MessageType.GET_DATA:
                (
                    exposure_status_code,
                    exposure_time_microseconds,
                    encoded_exponent,
                    serial_number,
                    ex_info,
                ) = struct.unpack_from("<BIHIQ", data)

                encoded_spectrum = [item[0] for item in struct.iter_unpack("<H", data[19:])]

                message["exposure_status"] = ExposureStatus(exposure_status_code)
                message["exposure_time"] = exposure_time_microseconds / 1000
                message["spectrum"] = self._decode_spectrum(
                    encoded_spectrum,
                    encoded_exponent,
                    message["exposure_time"],
                    serial_number,
                    ex_info,
                )

        return message


    def _parse_messages(self, data, max_messages=1):
        """Parse messages from datastream, return remainder and list of messages"""
        messages = []

        while len(data) >= 5:
            if not data.startswith(b"\xCC\x81"):
                raise ValueError("Invalid start bytes")

            length = int.from_bytes(data[2:5], "little")

            if len(data) < length:
                break

            if self._calculate_checksum(data[: length - 3]) != data[length - 3]:
                raise ValueError("Invalid checksum")

            if data[length - 2 : length] != b"\x0D\x0A":
                raise ValueError("Invalid end bytes")

            messages.append(self._parse_message(MessageType(data[5]), data[6 : 6 + length - 9]))
            data = data[length:]
            if len(messages) >= max_messages:
                break

        if messages:
            LOGGER.debug('parsed %s', messages)
        return (data, messages)
