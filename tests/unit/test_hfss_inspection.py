import pytest

from qresaudit.models.common import SolutionKind
from qresaudit_hfss.inspect import map_solution_kind


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Modal", SolutionKind.DRIVEN_MODAL),
        ("DrivenModal", SolutionKind.DRIVEN_MODAL),
        ("Driven Modal", SolutionKind.DRIVEN_MODAL),
        ("Terminal", SolutionKind.DRIVEN_TERMINAL),
        ("DrivenTerminal", SolutionKind.DRIVEN_TERMINAL),
        ("Driven Terminal", SolutionKind.DRIVEN_TERMINAL),
        ("Eigenmode", SolutionKind.EIGENMODE),
    ],
)
def test_solution_kind_aliases(raw: str, expected: SolutionKind) -> None:
    assert map_solution_kind(raw) is expected


@pytest.mark.parametrize("raw", ["", "Transient", "Modal Network", "Not Eigenmode"])
def test_unknown_solution_kind_is_not_guessed(raw: str) -> None:
    assert map_solution_kind(raw) is None
