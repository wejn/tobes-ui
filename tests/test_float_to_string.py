import math
import pytest

from tobes_ui.calibration.common import float_to_string

test_numbers = [
    123.456789,      # Regular positive number
    0.000123456789,  # Small positive number
    1234567890,      # Large positive number
    0,               # Zero
    1e-10,           # Very small positive number
    1e+10,           # Very large positive number
    -123.456789,     # Regular negative number
    -0.000123456789, # Small negative number
    -1e-10,          # Very small negative number
    -1e+10,          # Very large negative number
    0.1,             # Simple positive decimal
    -0.1,            # Simple negative decimal
    1e+100,          # Extremely large number
    1e-100,          # Extremely small number
    math.pi,         # Known irrational number
    math.e,          # Known constant
    math.sqrt(2),    # Known constant
]

test_lengths = {
    9: 5e-3,
    11: 1e-4,
    14: 1e-8,
    17: 1e-12,
}

@pytest.mark.parametrize("num", test_numbers)
@pytest.mark.parametrize("max_len, delta", test_lengths.items())
def test_float_to_string(num, max_len, delta):
    result = float_to_string(num, max_len)

    assert len(result) <= max_len, f"len wrong for {num}: is {len(result)}, expected ≤ {max_len}"

    result_float = float(result)
    if num == 0:
        assert result_float == 0, f"delta failed for 0: is {result}"
    else:
        rel_error = abs(result_float - num) / abs(num)
        assert rel_error < delta, (
                f"relative error for {num}: is {rel_error}, expected < {delta}")
