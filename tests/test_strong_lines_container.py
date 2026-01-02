"""Test for tobes_ui/strong_lines_container.py"""

# pylint: disable=missing-class-docstring,missing-function-docstring

import unittest
from tobes_ui.strong_lines import StrongLine
from tobes_ui.strong_lines_container import StrongLinesContainer


class TestStrongLinesContainer(unittest.TestCase):

    def setUp(self):
        # Prepare test data
        self.data = {
            "He": [
                StrongLine("He", 501.6, 15, "", 1),
                StrongLine("He", 447.1, 5, "", 1),
            ],
            "H": [
                StrongLine("H", 434.0, 12, "", 1),
                StrongLine("H", 410.2, 8, "", 1),
            ],
        }
        self.expected_plot_data = [
                [410.2, 434.0, 447.1, 501.6],
                [8, 12, 5, 15],
        ]
        self.container = StrongLinesContainer(self.data)

    def test_find_in_range_typical(self):
        # Range covering some lines
        result = self.container.find_in_range(430, 450)
        expected_wavelengths = [434.0, 447.1]
        self.assertEqual([line.wavelength for line in result], expected_wavelengths)

    def test_find_in_range_edge_inclusive(self):
        # Should include min and max if exactly matching keys
        result = self.container.find_in_range(410.2, 447.1)
        expected_wavelengths = [410.2, 434.0, 447.1]
        self.assertEqual([line.wavelength for line in result], expected_wavelengths)

    def test_find_in_range_single_element(self):
        # Range that matches exactly one line
        result = self.container.find_in_range(447.1, 447.1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].wavelength, 447.1)

    def test_find_in_range_no_elements(self):
        # Range with no matching lines
        result = self.container.find_in_range(411, 433.9)
        self.assertEqual(result, [])

    def test_find_in_range_below_min(self):
        # Range entirely below first line
        result = self.container.find_in_range(0, 400)
        self.assertEqual(result, [])

    def test_find_in_range_above_max(self):
        # Range entirely above last line
        result = self.container.find_in_range(600, 700)
        self.assertEqual(result, [])

    def test_plot_data_integrity(self):
        keys, values = self.container.plot_data()
        self.assertEqual(keys, self.expected_plot_data[0])
        self.assertEqual(values, self.expected_plot_data[1])

    def test_empty_container(self):
        empty_container = StrongLinesContainer({})
        self.assertEqual(empty_container.find_in_range(0, 1000), [])
        keys, values = empty_container.plot_data()
        self.assertEqual(keys, [])
        self.assertEqual(values, [])

    def test_len(self):
        self.assertEqual(len(self.container), 4)
        empty_container = StrongLinesContainer({})
        self.assertEqual(len(empty_container), 0)

    def test_plot_data_with_range(self):
        keys, values = self.container.plot_data(430, 450)
        self.assertEqual(keys, [434.0, 447.1])
        self.assertEqual(values, [12, 5])

    def test_plot_data_with_min_only(self):
        keys, values = self.container.plot_data(min_val=447.1)
        self.assertEqual(keys, [447.1, 501.6])
        self.assertEqual(values, [5, 15])

    def test_plot_data_with_max_only(self):
        keys, values = self.container.plot_data(max_val=434.0)
        self.assertEqual(keys, [410.2, 434.0])
        self.assertEqual(values, [8, 12])

    def test_plot_data_out_of_range(self):
        keys, values = self.container.plot_data(600, 700)
        self.assertEqual(keys, [])
        self.assertEqual(values, [])


if __name__ == "__main__":
    unittest.main()
