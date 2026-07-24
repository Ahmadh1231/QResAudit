import pytest

from qresaudit_hfss.inspect import axis_count


def test_axis_count() -> None:
    assert axis_count(0, 1, 0.25) == 5
    with pytest.raises(ValueError):
        axis_count(1, 0, 0.1)
    with pytest.raises(ValueError):
        axis_count(0, 1, 0)
