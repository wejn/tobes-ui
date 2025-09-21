"""Loads Hopoocolor (HPCS-3[23]0) CSV as Tobes Spectrum"""

# pylint: disable=too-many-statements,too-many-branches,too-many-locals

import csv
from datetime import datetime

from tobes_ui.loader import Loader
from tobes_ui.logger import LOGGER
from tobes_ui.spectrometer import ExposureMode, ExposureStatus, Spectrum

class HopooLoader(Loader, registered_types=['hpcs']):
    """Load hpcs csv for hpcs320 and 330 as tobes Spectrum"""
    @classmethod
    def load(cls, file: str) -> "Spectrum":
        spd = {}
        int_time = None
        device = None
        name = None
        date = None
        time_ = None
        last_wl = None # last wavelength encountered

        try:
            with open(file, newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                for line in reader:
                    if not line:
                        continue
                    first = line[0]
                    if first.startswith("Types"):
                        device = line[1]
                    elif first.startswith("Describe"):
                        name = line[1]
                    elif first.lower().startswith("test date"):
                        date = line[1]
                    elif first.lower().startswith("test time"):
                        time_ = line[1]
                    elif "Integral" in first and "Time" in first:
                        try:
                            int_time = float(line[1])
                        except (ValueError, IndexError):
                            pass
                    elif first.isdigit():
                        try:
                            wavelength = int(first)
                            if last_wl is not None and wavelength < last_wl:
                                # flicker section?
                                continue
                            spd[wavelength] = float(line[1])
                            last_wl = wavelength
                        except (ValueError, IndexError):
                            pass
        except OSError as exc:
            LOGGER.debug("Error: Couldn't read input CSV: %s", exc)
            raise ValueError(f"Can't read {file}: {exc}") from exc

        if date and time_:
            try:
                snap_time = datetime.strptime(f"{date} {time_}", "%Y-%m-%d %H:%M:%S")
            except ValueError as exc:
                raise ValueError(f"Can't read {file}: can't parse timestamp: {exc}") from exc
        else:
            raise ValueError(f"Can't read {file}: not enough data for timestamp") from exc

        wl_raw = list(spd.keys())
        return Spectrum(
            status=ExposureStatus.NORMAL,
            exposure=ExposureMode.AUTOMATIC,
            time=int_time,
            spd=spd,
            wavelength_range=range(int(min(wl_raw)), int(max(wl_raw))),
            wavelengths_raw=wl_raw,
            spd_raw=[v for k, v in spd.items()],
            ts=snap_time,
            name=name,
            device=device,
            y_axis="$μW\\cdot{}cm^{-2}\\cdot{}nm^{-1}$"
        )
