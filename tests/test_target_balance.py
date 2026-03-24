"""
Tests for ui/portfolio_planning.py target balance helpers.

Covers:
- _interpolate_target_balance: output length, start/end values, monotonicity
- _parse_target_balance_file: CSV parsing, column detection, error handling
"""
import io
import os
import tempfile
import pytest

from ui.portfolio_planning import _interpolate_target_balance, _parse_target_balance_file


# ---------------------------------------------------------------------------
# _interpolate_target_balance
# ---------------------------------------------------------------------------

class TestInterpolateTargetBalance:

    def test_output_length_default(self):
        vals = _interpolate_target_balance(100.0, 50.0)
        assert len(vals) == 120

    def test_output_length_custom(self):
        vals = _interpolate_target_balance(100.0, 50.0, n_months=60)
        assert len(vals) == 60

    def test_start_value(self):
        vals = _interpolate_target_balance(200.0, 100.0)
        assert abs(vals[0] - 200.0) < 0.01, f"Start should be 200.0, got {vals[0]}"

    def test_end_value(self):
        vals = _interpolate_target_balance(200.0, 100.0)
        assert abs(vals[-1] - 100.0) < 0.01, f"End should be 100.0, got {vals[-1]}"

    def test_increasing_trajectory(self):
        vals = _interpolate_target_balance(50.0, 150.0)
        # Values should be non-decreasing (linear interpolation)
        for i in range(1, len(vals)):
            assert vals[i] >= vals[i - 1] - 0.01, (
                f"Value decreased at month {i}: {vals[i-1]:.2f} → {vals[i]:.2f}"
            )

    def test_decreasing_trajectory(self):
        vals = _interpolate_target_balance(150.0, 50.0)
        for i in range(1, len(vals)):
            assert vals[i] <= vals[i - 1] + 0.01, (
                f"Value increased at month {i}: {vals[i-1]:.2f} → {vals[i]:.2f}"
            )

    def test_flat_trajectory(self):
        vals = _interpolate_target_balance(100.0, 100.0)
        for v in vals:
            assert abs(v - 100.0) < 0.01, f"Flat trajectory should stay at 100.0, got {v}"

    def test_returns_list_of_floats(self):
        vals = _interpolate_target_balance(100.0, 50.0)
        assert isinstance(vals, list)
        for v in vals:
            assert isinstance(v, float), f"Expected float, got {type(v)}: {v}"

    def test_values_are_rounded(self):
        """Values should be rounded to 2 decimal places."""
        vals = _interpolate_target_balance(100.0, 33.33)
        for v in vals:
            assert round(v, 2) == v, f"Value not rounded to 2 decimals: {v}"

    def test_zero_start(self):
        vals = _interpolate_target_balance(0.0, 100.0)
        assert abs(vals[0] - 0.0) < 0.01
        assert abs(vals[-1] - 100.0) < 0.01

    def test_single_month(self):
        vals = _interpolate_target_balance(75.0, 75.0, n_months=1)
        assert len(vals) == 1
        assert abs(vals[0] - 75.0) < 0.01


# ---------------------------------------------------------------------------
# _parse_target_balance_file
# ---------------------------------------------------------------------------

def _write_csv(content: str) -> str:
    """Write content to a temp CSV file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


class TestParseTargetBalanceFile:

    def test_none_path_returns_error(self):
        vals, msg = _parse_target_balance_file(None)
        assert vals is None
        assert len(msg) > 0

    def test_empty_path_returns_error(self):
        vals, msg = _parse_target_balance_file("")
        assert vals is None

    def test_named_column_target(self):
        csv_content = "target\n" + "\n".join(str(i * 10.0) for i in range(1, 121))
        path = _write_csv(csv_content)
        try:
            vals, msg = _parse_target_balance_file(path)
            assert vals is not None, f"Parse failed: {msg}"
            assert len(vals) == 120
        finally:
            os.unlink(path)

    def test_named_column_balance(self):
        csv_content = "balance\n" + "\n".join(str(100.0 - i * 0.5) for i in range(120))
        path = _write_csv(csv_content)
        try:
            vals, msg = _parse_target_balance_file(path)
            assert vals is not None, f"Parse failed: {msg}"
            assert len(vals) == 120
        finally:
            os.unlink(path)

    def test_single_numeric_column_no_header(self):
        csv_content = "\n".join(str(float(i)) for i in range(1, 121))
        path = _write_csv(csv_content)
        try:
            vals, msg = _parse_target_balance_file(path)
            assert vals is not None, f"Parse failed: {msg}"
            assert len(vals) == 120
        finally:
            os.unlink(path)

    def test_too_few_rows_returns_error(self):
        csv_content = "target\n" + "\n".join("10.0" for _ in range(5))
        path = _write_csv(csv_content)
        try:
            vals, msg = _parse_target_balance_file(path)
            assert vals is None, "Should fail with < 12 rows"
            assert "only" in msg.lower() or "need" in msg.lower() or "12" in msg
        finally:
            os.unlink(path)

    def test_excess_rows_truncated_to_120(self):
        csv_content = "target\n" + "\n".join("50.0" for _ in range(200))
        path = _write_csv(csv_content)
        try:
            vals, msg = _parse_target_balance_file(path)
            assert vals is not None, f"Parse failed: {msg}"
            assert len(vals) == 120
        finally:
            os.unlink(path)

    def test_short_series_interpolated_to_120(self):
        """A series with 24 rows should be interpolated to 120."""
        csv_content = "target\n" + "\n".join(str(float(i)) for i in range(24))
        path = _write_csv(csv_content)
        try:
            vals, msg = _parse_target_balance_file(path)
            assert vals is not None, f"Parse failed: {msg}"
            assert len(vals) == 120
        finally:
            os.unlink(path)

    def test_returns_list_of_floats(self):
        csv_content = "value\n" + "\n".join("100.0" for _ in range(120))
        path = _write_csv(csv_content)
        try:
            vals, msg = _parse_target_balance_file(path)
            assert vals is not None
            assert isinstance(vals, list)
            for v in vals:
                assert isinstance(v, float)
        finally:
            os.unlink(path)

    def test_no_numeric_column_returns_error(self):
        csv_content = "label\nfoo\nbar\nbaz\n" * 40
        path = _write_csv(csv_content)
        try:
            vals, msg = _parse_target_balance_file(path)
            assert vals is None
        finally:
            os.unlink(path)

    def test_success_message_mentions_column(self):
        csv_content = "target\n" + "\n".join("75.0" for _ in range(120))
        path = _write_csv(csv_content)
        try:
            vals, msg = _parse_target_balance_file(path)
            assert vals is not None
            assert "target" in msg.lower(), f"Message should mention column name: {msg}"
        finally:
            os.unlink(path)
