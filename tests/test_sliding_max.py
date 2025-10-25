import unittest
from tobes_ui.common import SlidingMax

class TestSlidingMax(unittest.TestCase):
    def test_basic_behavior(self):
        sm = SlidingMax(window_size=3)
        self.assertEqual(sm.add(1), 1)   # [1]
        self.assertEqual(sm.add(3), 3)   # [1,3]
        self.assertEqual(sm.add(2), 3)   # [1,3,2]
        self.assertEqual(sm.add(5), 5)   # [3,2,5]
        self.assertEqual(sm.add(4), 5)   # [2,5,4]
        self.assertEqual(sm.current_max, 5)

    def test_sliding_window_eviction(self):
        sm = SlidingMax(window_size=2)
        self.assertEqual(sm.add(1), 1)
        self.assertEqual(sm.add(5), 5)
        self.assertEqual(sm.add(2), 5)   # [5,2]
        self.assertEqual(sm.add(0), 2)   # [2,0] -> 2 is max
        self.assertEqual(sm.add(3), 3)   # [0,3] -> 3 is max

    def test_monotonic_decreasing_queue(self):
        sm = SlidingMax(window_size=3)
        sm.add(5)
        sm.add(4)
        sm.add(3)
        self.assertEqual(list(sm._decreasing), [5,4,3])
        sm.add(6)
        self.assertEqual(list(sm._decreasing), [6])
        self.assertEqual(sm.current_max, 6)

    def test_dynamic_resize_larger(self):
        sm = SlidingMax(window_size=2)
        sm.add(1)
        sm.add(3)
        sm.window_size = 4  # increase size
        sm.add(2)
        sm.add(5)
        self.assertEqual(sm.current_max, 5)
        self.assertEqual(len(sm._data), 4)

    def test_dynamic_resize_smaller(self):
        sm = SlidingMax(window_size=4)
        sm.add(1)
        sm.add(3)
        sm.add(2)
        sm.add(5)
        sm.window_size = 2  # shrink window
        # Oldest two values (1,3) removed
        self.assertEqual(list(sm._data), [2,5])
        self.assertEqual(sm.current_max, 5)

    def test_invalid_window_size(self):
        sm = SlidingMax(window_size=3)
        with self.assertRaises(ValueError):
            sm.window_size = 0

    def test_current_max_empty(self):
        sm = SlidingMax(window_size=3)
        self.assertIsNone(sm.current_max)

    def test_repeat_values(self):
        sm = SlidingMax(window_size=3)
        self.assertEqual(sm.add(2), 2)
        self.assertEqual(sm.add(2), 2)
        self.assertEqual(sm.add(2), 2)
        self.assertEqual(sm.add(2), 2)
        self.assertEqual(sm.current_max, 2)
        self.assertEqual(list(sm._decreasing), [2, 2, 2])

if __name__ == "__main__":
    unittest.main()
