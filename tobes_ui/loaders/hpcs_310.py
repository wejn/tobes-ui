"""
Loads Hopoocolor HPCS-310 CSV export as Tobes Spectrum

File layout
-----------

    Parameter,Value
    <label>,<value>             scalar fields: device, date, photometric, CRI
    <blank line>
    Wavelength (nm),Intensity
    <nm>,<intensity>            one row per nm
    <blank line>
    Timestamp,Lux Over Time
    <ISO 8601 UTC>,<lux>        illuminance history

The export carries no integration time, so Spectrum.time is None.
The scalar fields are kept under their original labels in meta["parameters"].
"""

import csv
import re
from datetime import datetime
from pathlib import Path

from tobes_ui.loader import Loader
from tobes_ui.logger import LOGGER
from tobes_ui.spectrometer import ExposureMode, ExposureStatus, Spectrum

_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "january", "february", "march", "april", "may", "june", "july",
            "august", "september", "october", "november", "december",
        ),
        start=1,
    )
}

# e.g. "October 27, 2026 - 10:07 PM"; parsed by hand to stay locale-independent
_DATE_RE = re.compile(
    r"^\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s*-\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])\s*$"
)

_CRI_RA_KEY = "CRI (Ra)"
_CRI_KEY_RE = re.compile(r"^R\d+$")

_SECTION_HEADERS = {
    "parameter": "params",
    "wavelength (nm)": "spd",
    "timestamp": "lux",
}


def _parse_date(value: str) -> datetime:
    match = _DATE_RE.match(value)
    if not match:
        raise ValueError(f"unrecognized date {value!r}")
    month_name, day, year, hour, minute, meridiem = match.groups()
    month = _MONTHS.get(month_name.lower())
    if month is None:
        raise ValueError(f"unknown month {month_name!r}")
    hour = int(hour)
    if not 1 <= hour <= 12:
        raise ValueError(f"hour out of range in {value!r}")
    hour = hour % 12 + (12 if meridiem.lower() == "pm" else 0)
    return datetime(int(year), month, int(day), hour, int(minute))


def _to_number(text: str) -> float | str:
    try:
        return float(text)
    except ValueError:
        return text


def _parse_spd_row(row: list[str], line_num: int) -> tuple[int, float]:
    try:
        wavelength = float(row[0])
        intensity = float(row[1])
    except (ValueError, IndexError) as exc:
        raise ValueError(f"malformed spectrum row at line {line_num}: {row!r}") from exc
    if not wavelength.is_integer():
        raise ValueError(f"non-integer wavelength at line {line_num}: {row[0]!r}")
    return int(wavelength), intensity


class Hpcs310Loader(Loader, registered_types=['hpcs310', 'hpcs310-csv']):
    """Load HPCS-310 csv export as tobes Spectrum"""

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements

    @classmethod
    def load(cls, file: str) -> "Spectrum":
        path = Path(file).expanduser()
        if not path.is_file():
            raise ValueError(f"Can't read {file}: not a file")

        params: dict[str, str] = {}
        spd: dict[int, float] = {}
        lux_over_time: list[tuple[str, float]] = []
        section = None
        started = False

        try:
            with open(path, newline='', encoding='utf-8-sig') as csvfile:
                reader = csv.reader(csvfile)
                for row in reader:
                    if not any(cell.strip() for cell in row):
                        section = None
                        continue

                    first = row[0].strip()

                    if not started:
                        if [cell.strip() for cell in row[:2]] != ["Parameter", "Value"]:
                            raise ValueError(f"Can't read {file}: not an HPCS-310 csv")
                        started = True

                    if section is None:
                        section = _SECTION_HEADERS.get(first.lower(), "ignored")
                        if section == "ignored":
                            LOGGER.debug("Ignoring unknown section %r at line %d",
                                         first, reader.line_num)
                        continue

                    if section == "params":
                        if len(row) >= 2:
                            # values may contain unquoted commas (e.g. the date)
                            params[first] = ",".join(row[1:]).strip()
                    elif section == "spd":
                        wavelength, intensity = _parse_spd_row(row, reader.line_num)
                        spd[wavelength] = intensity
                    elif section == "lux":
                        try:
                            lux_over_time.append((first, float(row[1])))
                        except (ValueError, IndexError):
                            LOGGER.debug("Skipping malformed lux row at line %d: %r",
                                         reader.line_num, row)
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            LOGGER.debug("Error: Couldn't read input CSV: %s", exc)
            raise ValueError(f"Can't read {file}: {exc}") from exc

        if not spd:
            raise ValueError(f"Can't read {file}: no spectrum data")

        date = params.pop("Date", None)
        if date is None:
            raise ValueError(f"Can't read {file}: not enough data for timestamp")
        try:
            snap_time = _parse_date(date)
        except ValueError as exc:
            raise ValueError(f"Can't read {file}: can't parse timestamp: {exc}") from exc

        name = params.pop("Device Name", None)
        device = params.pop("Device Type", None)

        cri: dict[str, float | str] = {}
        if _CRI_RA_KEY in params:
            cri["Ra"] = _to_number(params.pop(_CRI_RA_KEY))
        for key in [key for key in params if _CRI_KEY_RE.match(key)]:
            cri[key] = _to_number(params.pop(key))

        spd = dict(sorted(spd.items()))

        return Spectrum(
            status=ExposureStatus.NORMAL,
            exposure=ExposureMode.AUTOMATIC,
            time=1,  # Fake: There's no field in CSV for this
            spd=spd,
            wavelength_range=range(min(spd), max(spd)),
            wavelengths_raw=list(spd.keys()),
            spd_raw=list(spd.values()),
            ts=snap_time,
            name=name,
            device=device,
            y_axis="Intensity",
            meta={
                "parameters": {key: _to_number(value) for key, value in params.items()},
                "cri": cri,
                "lux_over_time": lux_over_time,
            },
        )
