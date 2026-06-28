"""
tests.test_sweep_tasks
----------------------
Unit tests for app/tasks/sweep_tasks.py — specifically the parameter
combination generator. (The full Celery task is integration-tested via
the API, not unit-tested here.)
"""
import pytest

from app.tasks.sweep_tasks import _generate_param_combinations


class TestGenerateParamCombinations:
    def test_empty_returns_single_empty_dict(self):
        result = _generate_param_combinations([])
        assert result == [{}]

    def test_single_parameter(self):
        result = _generate_param_combinations([
            {"key": "stddev_min_pct", "values": [0.01, 0.02, 0.03]},
        ])
        assert len(result) == 3
        assert {"stddev_min_pct": 0.01} in result
        assert {"stddev_min_pct": 0.02} in result
        assert {"stddev_min_pct": 0.03} in result

    def test_two_parameters_cartesian_product(self):
        result = _generate_param_combinations([
            {"key": "lookback_low", "values": [5, 8]},
            {"key": "stddev_min_pct", "values": [0.01, 0.02]},
        ])
        assert len(result) == 4  # 2 × 2
        assert {"lookback_low": 5, "stddev_min_pct": 0.01} in result
        assert {"lookback_low": 5, "stddev_min_pct": 0.02} in result
        assert {"lookback_low": 8, "stddev_min_pct": 0.01} in result
        assert {"lookback_low": 8, "stddev_min_pct": 0.02} in result

    def test_three_values(self):
        result = _generate_param_combinations([
            {"key": "profit_target", "values": [100, 200, 300]},
        ])
        assert len(result) == 3

    def test_mixed_int_float_string_values(self):
        result = _generate_param_combinations([
            {"key": "option_type", "values": ["CE", "PE"]},
            {"key": "strike_offset", "values": [0, 1, -1]},
        ])
        assert len(result) == 6  # 2 × 3
        assert {"option_type": "CE", "strike_offset": 0} in result
        assert {"option_type": "PE", "strike_offset": -1} in result

    def test_single_value(self):
        result = _generate_param_combinations([
            {"key": "sma_trend", "values": [70]},
        ])
        assert result == [{"sma_trend": 70}]
