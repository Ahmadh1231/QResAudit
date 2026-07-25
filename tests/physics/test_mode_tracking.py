"""Mode-overlap and assignment tests."""

import numpy as np

from qresaudit.analysis.mode_tracking import assign_modes, field_overlap, propagate_branch_ids


def test_overlap_is_phase_invariant_and_permittivity_normalized() -> None:
    coordinates = np.column_stack((np.arange(4), np.zeros(4), np.zeros(4)))
    values = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]] * 2, dtype=complex)

    overlap = field_overlap(
        coordinates,
        values,
        coordinates,
        values * np.exp(1j * 1.13),
        epsilon_r=11.7,
    )

    assert np.isclose(overlap, 1.0)


def test_assignment_tracks_swapped_modes() -> None:
    assignments, confidence = assign_modes(np.asarray([[0.02, 0.99], [0.98, 0.01]]))

    assert assignments == [1, 0]
    assert confidence > 0.98


def test_branch_identity_survives_repeated_raw_mode_reordering() -> None:
    branch_ids = [0, 1, 2]
    branch_ids = propagate_branch_ids(branch_ids, [1, 0, 2])
    branch_ids = propagate_branch_ids(branch_ids, [2, 1, 0])

    assert branch_ids == [2, 0, 1]
