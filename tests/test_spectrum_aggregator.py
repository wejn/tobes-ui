"""Tests for SpectrumAggregator from tobes_ui/common.py."""

# pylint: disable=missing-class-docstring,missing-function-docstring,redefined-outer-name

from dataclasses import dataclass
import numpy as np
import pytest

from tobes_ui.common import SpectrumAggregator


@dataclass
class Spectrum:
    spd: dict[int, float]
    spd_raw: list[float]
    y_axis: str


def spectrum(spd_data, spd_raw, y_axis='bar'):
    """Convenience method to spin up the proper shape of Spectrum"""
    return Spectrum(
            spd=dict(zip(list(range(0,len(spd_data))), spd_data)),
            spd_raw=spd_raw,
            y_axis=y_axis,
    )


class TestSpectrumAggregator:

    def test_avg_basic(self):
        aggregator_avg = SpectrumAggregator(window_size=3, func="avg")
        data1 = spectrum([1.0, 2.0], [1.5, 2.5])
        data2 = spectrum([3.0, 4.0], [3.5, 4.5])

        result1 = aggregator_avg.add(data1)
        np.testing.assert_array_equal(list(result1.spd.values()), [1.0, 2.0])
        np.testing.assert_array_equal(result1.spd_raw, [1.5, 2.5])

        result2 = aggregator_avg.add(data2)
        np.testing.assert_array_almost_equal(list(result2.spd.values()), [2.0, 3.0])
        np.testing.assert_array_almost_equal(result2.spd_raw, [2.5, 3.5])

    def test_max_basic(self):
        aggregator_max = SpectrumAggregator(window_size=3, func="max")

        data1 = spectrum([1.0, 2.0], [1.5, 2.5])
        data2 = spectrum([3.0, 4.0], [3.5, 4.5])

        result1 = aggregator_max.add(data1)
        np.testing.assert_array_equal(list(result1.spd.values()), [1.0, 2.0])
        np.testing.assert_array_equal(result1.spd_raw, [1.5, 2.5])

        result2 = aggregator_max.add(data2)
        np.testing.assert_array_equal(list(result2.spd.values()), [3.0, 4.0])
        np.testing.assert_array_equal(result2.spd_raw, [3.5, 4.5])

    def test_window_size_enforcement(self):
        aggregator_avg = SpectrumAggregator(window_size=3, func="avg")

        for i in range(5):
            data = spectrum([float(i)], [float(i + 0.5)])
            aggregator_avg.add(data)

        result = aggregator_avg.add(spectrum([5.0], [5.5]))
        np.testing.assert_array_almost_equal(list(result.spd.values()), [4.0])
        np.testing.assert_array_almost_equal(result.spd_raw, [4.5])

    def test_change_window_size(self):
        aggregator_avg = SpectrumAggregator(window_size=3, func="avg")

        for i in range(4):
            data = spectrum([float(i)], [float(i + 0.5)])
            aggregator_avg.add(data)

        aggregator_avg.window_size = 2
        result = aggregator_avg.add(spectrum([4.0], [4.5]))
        np.testing.assert_array_almost_equal(list(result.spd.values()), [3.5])
        np.testing.assert_array_almost_equal(result.spd_raw, [4.0])

    def test_change_op_runtime(self):
        aggregator_avg = SpectrumAggregator(window_size=3, func="avg")

        data1 = spectrum([1.0, 2.0], [1.5, 2.5])
        data2 = spectrum([3.0, 4.0], [3.5, 4.5])

        aggregator_avg.add(data1)
        aggregator_avg.add(data2)

        aggregator_avg.func = "max"
        result = aggregator_avg.add(spectrum([2.0, 3.0], [2.5, 3.5]))
        np.testing.assert_array_equal(list(result.spd.values()), [3.0, 4.0])
        np.testing.assert_array_equal(result.spd_raw, [3.5, 4.5])

    def test_window_size_one(self):
        agg = SpectrumAggregator(window_size=1, func="avg")

        data1 = spectrum([1.0, 2.0], [1.5, 2.5])
        data2 = spectrum([3.0, 4.0], [3.5, 4.5])

        result1 = agg.add(data1)
        np.testing.assert_array_equal(list(result1.spd.values()), [1.0, 2.0])

        result2 = agg.add(data2)
        np.testing.assert_array_equal(list(result2.spd.values()), [3.0, 4.0])

    def test_invalid_window_size(self):
        aggregator_avg = SpectrumAggregator(window_size=3, func="avg")

        with pytest.raises(ValueError, match="window_size must be positive"):
            aggregator_avg.window_size = 0

        with pytest.raises(ValueError, match="window_size must be positive"):
            aggregator_avg.window_size = -1

    def test_invalid_op(self):
        aggregator_avg = SpectrumAggregator(window_size=3, func="avg")

        with pytest.raises(ValueError, match="func must be 'avg' or 'max'"):
            aggregator_avg.func = "min"

    def test_empty_buffer_handling(self):
        aggregator_avg = SpectrumAggregator(window_size=3, func="avg")

        data = spectrum([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
        result = aggregator_avg.add(data)

        np.testing.assert_array_equal(list(result.spd.values()), [1.0, 2.0, 3.0])
        np.testing.assert_array_equal(result.spd_raw, [4.0, 5.0, 6.0])

    def test_large_window_avg(self):
        agg = SpectrumAggregator(window_size=100, func="avg")

        values = []
        for i in range(50):
            data = spectrum([float(i)], [float(i * 2)])
            result = agg.add(data)
            values.append(i)

        expected_avg = np.mean(values)
        np.testing.assert_array_almost_equal(list(result.spd.values()), [expected_avg])

    def test_data_independence(self):
        aggregator_avg = SpectrumAggregator(window_size=3, func="avg")

        data = spectrum([1.0, 2.0], [3.0, 4.0])
        aggregator_avg.add(data)

        data.spd[1] = 999.0
        data.spd_raw[0] = 999.0

        result = aggregator_avg.add(spectrum([5.0, 6.0], [7.0, 8.0]))

        assert data.spd[1] == 999.0 and data.spd_raw[0] == 999.0
        np.testing.assert_array_equal(list(result.spd.values()), [3.0, 4.0])
        np.testing.assert_array_equal(result.spd_raw, [5.0, 6.0])

    def test_y_axis_altered(self):
        aggregator_avg = SpectrumAggregator(window_size=3, func="avg")

        data = spectrum([1.0, 2.0], [3.0, 4.0], 'fancy_y_axis')
        result = aggregator_avg.add(data)

        assert result.y_axis.startswith('fancy_y_axis')
        assert 'fancy_y_axis' != result.y_axis # info is appended to it, shouldn't be the same

    def test_clear(self):
        aggregator_avg = SpectrumAggregator(window_size=3, func="avg")

        aggregator_avg.add(spectrum([1.0, 2.0], [3.0, 4.0]))
        aggregator_avg.clear()

        data = spectrum([5.0, 6.0], [7.0, 8.0])
        result = aggregator_avg.add(data)

        np.testing.assert_array_equal(list(result.spd.values()), [5.0, 6.0])
        np.testing.assert_array_equal(result.spd_raw, [7.0, 8.0])
