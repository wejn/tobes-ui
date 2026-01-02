"""Tests for SlidingMax from tobes_ui/common.py"""

# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name

import unittest
from unittest.mock import patch

from tobes_ui.common import SlidingMax


class TestSlidingMax(unittest.TestCase):

    @patch('time.time')
    def test_single_value(self, mock_time):
        mock_time.return_value = 100.0
        sm = SlidingMax(window_size=10.0)
        self.assertEqual(sm.add(5.0), 5.0)

    @patch('time.time')
    def test_increasing_values(self, mock_time):
        sm = SlidingMax(window_size=10.0)

        mock_time.return_value = 100.0
        self.assertEqual(sm.add(1.0), 1.0)

        mock_time.return_value = 101.0
        self.assertEqual(sm.add(2.0), 2.0)

        mock_time.return_value = 102.0
        self.assertEqual(sm.add(3.0), 3.0)

    @patch('time.time')
    def test_decreasing_values(self, mock_time):
        sm = SlidingMax(window_size=10.0)

        mock_time.return_value = 100.0
        self.assertEqual(sm.add(5.0), 5.0)

        mock_time.return_value = 101.0
        self.assertEqual(sm.add(3.0), 5.0)

        mock_time.return_value = 102.0
        self.assertEqual(sm.add(1.0), 5.0)

    @patch('time.time')
    def test_mixed_values(self, mock_time):
        sm = SlidingMax(window_size=10.0)

        mock_time.return_value = 100.0
        self.assertEqual(sm.add(3.0), 3.0)

        mock_time.return_value = 101.0
        self.assertEqual(sm.add(5.0), 5.0)

        mock_time.return_value = 102.0
        self.assertEqual(sm.add(2.0), 5.0)

        mock_time.return_value = 103.0
        self.assertEqual(sm.add(7.0), 7.0)

        mock_time.return_value = 104.0
        self.assertEqual(sm.add(4.0), 7.0)

    @patch('time.time')
    def test_window_expiration(self, mock_time):
        sm = SlidingMax(window_size=5.0)

        mock_time.return_value = 100.0
        self.assertEqual(sm.add(10.0), 10.0)

        mock_time.return_value = 102.0
        self.assertEqual(sm.add(5.0), 10.0)

        mock_time.return_value = 105.5
        self.assertEqual(sm.add(3.0), 5.0)

        mock_time.return_value = 106.0
        self.assertEqual(sm.add(2.0), 5.0)

        mock_time.return_value = 108.0
        self.assertEqual(sm.add(1.0), 3.0)

        mock_time.return_value = 110.0
        self.assertEqual(sm.add(1.0), 3.0)

    @patch('time.time')
    def test_all_values_expire(self, mock_time):
        sm = SlidingMax(window_size=5.0)

        mock_time.return_value = 100.0
        self.assertEqual(sm.add(10.0), 10.0)

        mock_time.return_value = 101.0
        self.assertEqual(sm.add(8.0), 10.0)

        mock_time.return_value = 110.0
        self.assertEqual(sm.add(3.0), 3.0)

    @patch('time.time')
    def test_equal_values(self, mock_time):
        sm = SlidingMax(window_size=10.0)

        mock_time.return_value = 100.0
        self.assertEqual(sm.add(5.0), 5.0)

        mock_time.return_value = 101.0
        self.assertEqual(sm.add(5.0), 5.0)

        mock_time.return_value = 102.0
        self.assertEqual(sm.add(5.0), 5.0)

    @patch('time.time')
    def test_window_size_change_smaller(self, mock_time):
        sm = SlidingMax(window_size=10.0)

        mock_time.return_value = 100.0
        sm.add(10.0)

        mock_time.return_value = 105.0
        sm.add(5.0)

        mock_time.return_value = 108.0
        sm.add(3.0)

        mock_time.return_value = 110.0
        sm.window_size = 3.0

        mock_time.return_value = 110.5
        self.assertEqual(sm.add(2.0), 3.0)

    @patch('time.time')
    def test_window_size_change_larger(self, mock_time):
        sm = SlidingMax(window_size=5.0)

        mock_time.return_value = 100.0
        sm.add(10.0) # exp @ 105

        mock_time.return_value = 103.0
        sm.add(5.0) # exp @ 108

        mock_time.return_value = 107.0
        sm.window_size = 10.0 # now the 10.0 @ 100.0 exp @ 110

        mock_time.return_value = 107.5
        self.assertEqual(sm.add(3.0), 10.0)

        mock_time.return_value = 110.0
        self.assertEqual(sm.add(3.0), 5.0)

    @patch('time.time')
    def test_window_expiration_boundary(self, mock_time):
        sm = SlidingMax(window_size=5.0)

        mock_time.return_value = 100.0
        sm.add(10.0) # exp @ 105

        mock_time.return_value = 104.99999999999999
        self.assertEqual(sm.add(5.0), 10.0)

        mock_time.return_value = 105.1
        self.assertEqual(sm.add(3.0), 5.0)


if __name__ == '__main__':
    unittest.main()
