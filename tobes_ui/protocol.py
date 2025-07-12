"""Protocol parser for TorchBearer Spectrometer"""

from enum import Enum
import struct

from .logger import LOGGER

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


class ExposureMode(Enum):
    """Type of exposure mode"""
    MANUAL = 0x00
    AUTOMATIC = 0x01

    def __str__(self):
        """Convert to readable string"""
        return str(self.name).lower()


class ExposureStatus(Enum):
    """Status of exposure (in auto mode)"""
    NORMAL = 0x00
    OVER = 0x01
    UNDER = 0x02

    def __str__(self):
        """Convert to readable string"""
        return str(self.name).lower()


def _decode_spectrum(encoded_spectrum, encoded_exponent, exposure_time, serial, ex_info):
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


def _calculate_checksum(message):
    return sum(message) & 0xFF


def build_message(message_type, data):
    """Build message of given type with data as payload"""
    LOGGER.debug('%s %s', message_type, data)
    message = b"\xCC\x01"
    message += int.to_bytes(9 + len(data), 3, "little")
    message += int.to_bytes(message_type.value, 1, "little")
    message += data
    message += int.to_bytes(_calculate_checksum(message), 1, "little")
    message += b"\x0D\x0A"

    return message


def _parse_message(message_type, data):
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
            message["spectrum"] = _decode_spectrum(
                encoded_spectrum,
                encoded_exponent,
                message["exposure_time"],
                serial_number,
                ex_info,
            )

    return message


def parse_messages(data, max_messages=1):
    """Parse messages from datastream, return remainder and list of messages"""
    messages = []

    while len(data) >= 5:
        if not data.startswith(b"\xCC\x81"):
            raise ValueError("Invalid start bytes")

        length = int.from_bytes(data[2:5], "little")

        if len(data) < length:
            break

        if _calculate_checksum(data[: length - 3]) != data[length - 3]:
            raise ValueError("Invalid checksum")

        if data[length - 2 : length] != b"\x0D\x0A":
            raise ValueError("Invalid end bytes")

        messages.append(_parse_message(MessageType(data[5]), data[6 : 6 + length - 9]))
        data = data[length:]
        if len(messages) >= max_messages:
            break

    if messages:
        LOGGER.debug('parsed %s', messages)
    return (data, messages)
