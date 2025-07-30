#!/usr/bin/env python3
"""Converts Hopoocolor (HPCS-320) CSV to Tobes JSON"""
# pylint: disable=invalid-name

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys

from tobes_ui.protocol import ExposureMode, ExposureStatus
from tobes_ui.spectrometer import Spectrum

def parse_args():
    """Parse argv"""
    parser = argparse.ArgumentParser(description="Convert Hopoocolor (HPCS-320) CSV to Tobes JSON")

    parser.add_argument("input_csv", help="Path to the input CSV file.")
    parser.add_argument(
            "output_json",
            nargs="?",
            help="Path to the output JSON file. Defaults to input filename with .json extension."
    )

    return parser.parse_args()

def main():
    """Main"""
    args = parse_args()

    input_path = Path(args.input_csv)
    output_path = Path(args.output_json) if args.output_json else (
        input_path.with_suffix('.json') if input_path.suffix.lower() == '.csv'
        else input_path.with_name(input_path.name + '.json')
    )

    spd = {}
    int_time = None
    device = None
    name = None
    date = None
    time_ = None

    try:
        with open(input_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            for ln in reader:
                if not ln:
                    continue
                first = ln[0]
                if first.startswith("Types"):
                    device = ln[1]
                elif first.startswith("Describe"):
                    name = ln[1]
                elif first.lower().startswith("test date"):
                    date = ln[1]
                elif first.lower().startswith("test time"):
                    time_ = ln[1]
                elif "Integral" in first and "Time" in first:
                    try:
                        int_time = float(ln[1])
                    except (ValueError, IndexError):
                        pass
                elif first.isdigit():
                    try:
                        spd[int(first)] = float(ln[1])
                    except (ValueError, IndexError):
                        pass
    except OSError as exc:
        print(f"Error: Couldn't read input CSV: {exc}", file=sys.stderr)
        sys.exit(1)

    if date and time_:
        try:
            snap_time = datetime.strptime(f"{date} {time_}", "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            print(f"Error: Couldn't parse timestamp: {exc}", file=sys.stderr)
            sys.exit(2)
    else:
        print("Error: Not enough data for timestamp in the input file", file=sys.stderr)
        sys.exit(2)

    wl_raw = list(spd.keys())
    spectrum = Spectrum(
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

    try:
        with open(output_path, 'w', encoding='utf-8') as file:
            file.write(spectrum.to_json())
    except OSError as exc:
        print(f"Error: Couldn't write json: {exc}", file=sys.stderr)
        sys.exit(3)

    print('JSON written as:', output_path)


if __name__ == "__main__":
    main()
