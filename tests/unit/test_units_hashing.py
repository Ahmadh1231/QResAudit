from qresaudit.hashing import run_id_for
from qresaudit.units import canonical_variation, convert_to_si


def test_si_conversion() -> None:
    assert convert_to_si("2um") == 2e-6
    assert convert_to_si("6.2GHz") == 6.2e9


def test_variation_and_run_id_are_stable() -> None:
    assert canonical_variation({"b": "2um", "a": "1um"}) == "a=1um;b=2um"
    assert run_id_for({"b": 2, "a": 1}) == run_id_for({"a": 1, "b": 2})
