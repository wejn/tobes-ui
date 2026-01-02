"""Basic tests for strong lines."""

# pylint: disable=missing-class-docstring,missing-function-docstring

import unittest

from tobes_ui.strong_lines import (Flag, STRONG_LINES)


class TestStrongLines(unittest.TestCase):

    def test_flag_mapping(self):
        # Test that the flags map correctly from codes
        self.assertEqual(str(Flag.BAND_HEAD), 'b (band head)')
        self.assertEqual(str(Flag.PERSISTENT), 'P (a persistent line)')
        self.assertEqual(Flag.PERSISTENT.description, 'a persistent line')

    def test_flags_method(self):
        # Check that StrongLine.flags returns the correct Flag enums
        line = STRONG_LINES['C'].lines[0]  # This line has raw_flags="P"
        flags = line.flags()
        self.assertTrue(all(isinstance(f, Flag) for f in flags))
        self.assertIn(Flag.PERSISTENT, flags)

        # Check line with multiple flags, e.g. "Pc"
        line_pc = None
        for line in STRONG_LINES['C'].lines:
            if line.raw_flags == "Pc":
                line_pc = line
                break
        self.assertIsNotNone(line_pc)
        flags_pc = line_pc.flags()
        self.assertIn(Flag.PERSISTENT, flags_pc)
        self.assertIn(Flag.COMPLEX, flags_pc)

    def test_flags(self):
        line = STRONG_LINES["C"].lines[0]
        flags = line.flags()
        self.assertTrue(all(f in Flag for f in flags))
        self.assertTrue(any(f.code == 'P' for f in flags))

    def test_for_wavelength_range(self):
        strong_lines = STRONG_LINES["C"]
        wave_range = range(100, 133)
        lines_in_range = strong_lines.for_wavelength_range(wave_range)
        self.assertTrue(all(int(l.wavelength) in wave_range for l in lines_in_range))
        # note: conversion to int -> inclusive range
        persistent_lines_in_range = strong_lines.for_wavelength_range(
                wave_range, only_persistent=True)
        self.assertTrue(all(int(l.wavelength) in wave_range for l in persistent_lines_in_range))
        self.assertTrue(all('P' in l.raw_flags for l in persistent_lines_in_range))

    def test_for_intensity_range(self):
        strong_lines = STRONG_LINES["H"]
        intensity_range = range(10, 101)
        lines_in_range = strong_lines.for_intensity_range(intensity_range)
        self.assertTrue(all(int(l.intensity) in intensity_range for l in lines_in_range))
        persistent_lines_in_range = strong_lines.for_intensity_range(
                intensity_range, only_persistent=True)
        self.assertTrue(all(int(l.intensity) in intensity_range for l in persistent_lines_in_range))
        self.assertTrue(all('P' in l.raw_flags for l in persistent_lines_in_range))

    def test_for_wavelength_and_intensity_range(self):
        strong_lines = STRONG_LINES["H"]
        wave_range = range(90, 131)
        int_range = range(10, 61)
        filtered_lines = strong_lines.for_wavelength_and_intensity_range(wave_range, int_range)
        self.assertTrue(all(
            int(l.wavelength) in wave_range and int(l.intensity) in int_range
            for l in filtered_lines
        ))
        persistent_filtered = strong_lines.for_wavelength_and_intensity_range(
                wave_range, int_range, only_persistent=True)
        self.assertTrue(all('P' in l.raw_flags for l in persistent_filtered))


if __name__ == '__main__':
    unittest.main()
