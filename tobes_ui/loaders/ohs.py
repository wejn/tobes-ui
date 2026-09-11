"""
Loads Hopoocolor (HPCS-3[23]0) OHS as Tobes Spectrum

Confirmed against:
  HPCS-320  firmware 1.37.0  (2912 bytes)
  HPCS-330P firmware 2.0.8   (3796 bytes)

File layout
-----------
[Header]
  0x0000  10 bytes ASCII   Model name, null-padded  e.g. "HPCS-320\0\0", "HPCS-330P\0"
  0x000a  2 bytes  u16 LE  Firmware version as integer (1370 -> "1.37.0")
  0x000c  24 bytes ASCII   Description, null-padded

[Scalars] — all f32 LE, offset 0x0024
  330P inserts 15 plant/horticultural fields before the standard photometric block.
  Photometric:  E(lx), E(fc), CCT, Duv, CIE x/y/u/v/u'/v', SDCM  (11 fields)
  CRI:          Ra, R1–R15                                          (16 fields)
  Spectral:     [Ee], S/P, Dominant, Purity, HalfWidth, Peak,
                Center, Centroid, R%, G%, B%,
                [Freq, FlickPct, FlickerIdx, DutyCycle, FlickCycle], (5 flicker, 330P only)
                IntegralTime, PeakSignal, DarkSignal, CompensateLevel

[Datetime]
  10 bytes ASCII  YYYY-MM-DD  null-terminated
   8 bytes ASCII  HH:MM:SS    null-terminated

[SPD buffer]  671 × f32 LE, units mW/m²/nm
  Data fills from the start; unused slots are zero-padded.
  Recorded wavelength range is stored in the footer.

[Footer]
  4 bytes  f32 LE  start_wavelength (nm)
  4 bytes  f32 LE  end_wavelength   (nm)

[Raw counts]  330P only — 400 × u16 LE raw ADC detector values
"""

# pylint: disable=too-many-statements,too-many-branches,too-many-locals

import struct
from datetime import datetime
from pathlib import Path

from tobes_ui.loader import Loader
from tobes_ui.logger import LOGGER
from tobes_ui.spectrometer import ExposureMode, ExposureStatus, Spectrum

_HORTICULTURAL_FIELDS = [
    "PAR_mW_cm2",
    "PPFD_umol_m2_s",
    "PPFD_UV_umol_m2_s",
    "PPFD_B_umol_m2_s",
    "PPFD_G_umol_m2_s",
    "PPFD_R_umol_m2_s",
    "PPFD_FR_umol_m2_s",
    "PPFD_IR_umol_m2_s",
    "Kppfv_umol_s_klm",
    "Erb_ratio",
    "YPFD_umol_m2_s",
    "Ech_A_mW_cm2",
    "Ech_B_mW_cm2",
    "DLI_mol_m2d",
    "CLI_mol_m2",
]

_PHOTOMETRIC_FIELDS = [
    "E_lx",
    "E_fc",
    "CCT_K",
    "Duv",
    "CIE_x",
    "CIE_y",
    "CIE_u",
    "CIE_v",
    "CIE_u_prime",
    "CIE_v_prime",
    "SDCM",
]

_CRI_FIELDS = ["Ra"] + [f"R{i}" for i in range(1, 16)]

_SPECTRAL_STAT_FIELDS_COMMON_PRE = [
    "S_P_ratio",
    "dominant_nm",
    "purity_pct",
    "half_width_nm",
    "peak_nm",
    "center_nm",
    "centroid_nm",
    "R_ratio_pct",
    "G_ratio_pct",
    "B_ratio_pct",
]

_FLICKER_FIELDS = [
    "freq_Hz",
    "flicker_pct",
    "flicker_index",
    "duty_cycle_pct",
    "flick_cycle_ms",
]

_INSTRUMENT_FIELDS = [
    "integral_time_ms",
    "peak_signal",
    "dark_signal",
    "compensate_level",
]

_SPD_BUFFER_SLOTS = 671
_RAW_COUNT_SLOTS = 400  # 330P only

def _read_f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]

def _read_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]

def _read_cstring(data: bytes, offset: int, max_len: int) -> str:
    chunk = data[offset : offset + max_len]
    end = chunk.find(b"\x00")
    if end != -1:
        return chunk[:end].decode("ascii", errors="replace")
    return chunk.decode("ascii", errors="replace")

def _fmt_version(v: int) -> str:
    major = v // 1000
    rest = v % 1000
    minor = rest // 10
    patch = rest % 10
    return f"{major}.{minor}.{patch}"

class OhsFileLoader(Loader, registered_types=['ohs', 'hopoo-ohs']):
    """Load hpcs ohs for hpcs320 and 330p as tobes Spectrum"""
    @classmethod
    def load(cls, file: str) -> "Spectrum":
        data = None

        try:
            if not file.lower().endswith('.ohs'):
                raise ValueError("Paths that don't end with .ohs are not a good ohs source")

            expanded_path = Path(file).expanduser()

            if not expanded_path.is_file():
                raise ValueError("Non-file entities are not a good ohs source")

            data = expanded_path.read_bytes()
        except OSError as exc:
            LOGGER.debug("Error: Couldn't read input OHS: %s", exc)
            raise ValueError(f"Can't read {file}: {exc}") from exc

        # Header
        model = _read_cstring(data, 0x00, 10)  # e.g. "HPCS-320", "HPCS-330P"
        version_raw = struct.unpack_from("<H", data, 0x0A)[0]
        version_str = _fmt_version(version_raw)
        description = _read_cstring(data, 0x0C, 24)

        has_horticultural = model.endswith("P")  # present on 330P

        # Scalars
        offset = 0x24

        horticultural: dict = {}
        if has_horticultural:
            for name in _HORTICULTURAL_FIELDS:
                horticultural[name] = _read_f32(data, offset)
                offset += 4

        photometric: dict = {}
        for name in _PHOTOMETRIC_FIELDS:
            photometric[name] = _read_f32(data, offset)
            offset += 4

        cri: dict = {}
        for name in _CRI_FIELDS:
            cri[name] = _read_f32(data, offset)
            offset += 4

        ## Ee (irradiance, mW/cm²) — 330P only, sits before spectral stats
        irradiance: float | None = None
        if has_horticultural:
            irradiance = _read_f32(data, offset)
            offset += 4

        spectral_stats: dict = {}
        for name in _SPECTRAL_STAT_FIELDS_COMMON_PRE:
            spectral_stats[name] = _read_f32(data, offset)
            offset += 4

        flicker: dict | None = None
        if has_horticultural:
            flicker = {}
            for name in _FLICKER_FIELDS:
                flicker[name] = _read_f32(data, offset)
                offset += 4

        instrument: dict = {}
        for name in _INSTRUMENT_FIELDS:
            instrument[name] = _read_f32(data, offset)
            offset += 4

        # Datetime
        test_date = _read_cstring(data, offset, 10)
        offset += 11  # 10 chars + null
        test_time = _read_cstring(data, offset, 8)
        offset += 9   # 8 chars + null

        # SPD buffer (671 × f32, fixed size)
        spd_buf_start = offset
        spd_buf: list[float] = [
            _read_f32(data, spd_buf_start + i * 4)
            for i in range(_SPD_BUFFER_SLOTS)
        ]
        offset = spd_buf_start + _SPD_BUFFER_SLOTS * 4

        # Footer: start/end wavelength
        start_nm = int(_read_f32(data, offset))
        end_nm   = int(_read_f32(data, offset + 4))
        offset += 8

        n_samples = end_nm - start_nm + 1
        spd = {
            start_nm + i: spd_buf[i]
            for i in range(n_samples)
        }

        # Raw detector counts (330P only)
        raw_counts: list[int] | None = None
        if has_horticultural and offset + _RAW_COUNT_SLOTS * 2 <= len(data):
            raw_counts = [
                _read_u16(data, offset + i * 2)
                for i in range(_RAW_COUNT_SLOTS)
            ]

        # Assemble output
        photometric_out = {
            **photometric,
            "CRI": cri,
        }

        if horticultural:
            photometric_out["horticultural"] = horticultural
        if irradiance is not None:
            photometric_out["Ee_mW_cm2"] = irradiance

        spectral_out = {
            **spectral_stats,
            **instrument,
        }
        if raw_counts is not None:
            spectral_out["raw_counts"] = raw_counts

        metadata = {
            "model": model,
            "firmware_version": version_str,
            "photometric": photometric_out,
            "spectral": spectral_out,
        }
        if flicker:
            metadata["flicker"] = flicker

        return Spectrum(
            status=ExposureStatus.NORMAL,
            exposure=ExposureMode.AUTOMATIC,
            time=instrument["integral_time_ms"],
            spd=spd,
            wavelength_range=range(start_nm, end_nm),
            wavelengths_raw=list(spd.keys()),
            spd_raw=[v for k, v in spd.items()],
            ts=datetime.strptime(f"{test_date} {test_time}", "%Y-%m-%d %H:%M:%S"),
            name=description,
            device=f"{model} {version_str}",
            y_axis="$mW\\cdot{}m^{-2}\\cdot{}nm^{-1}$",
            meta=metadata,
        )
