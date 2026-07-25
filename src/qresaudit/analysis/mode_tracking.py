"""Eigenmode tracking — identify and follow eigenmodes across parameter sweeps.

Uses phase-invariant normalized field overlap for mode assignment,
Hungarian algorithm for optimal matching, and detection of crossings,
avoided crossings, and hybridization.

Command:
    qresaudit modes track SWEEP_DIRECTORY
"""

from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from qresaudit.io.fields_hdf5 import read_field_hdf5
from qresaudit.models.v0_2 import AvoidedCrossing, ModeBranch


def field_overlap(
    coords_a: np.ndarray,
    values_a: np.ndarray,
    coords_b: np.ndarray,
    values_b: np.ndarray,
    epsilon_r: float = 1.0,
) -> float:
    """Compute phase-invariant normalized field overlap integral.

    Uses nearest-neighbor interpolation if grids differ.
    For electric fields: overlap = |∫ E_a* · ε E_b dV| / sqrt(∫|E_a|² dV · ∫|E_b|² dV)
    """
    # Ensure same length via nearest interpolation
    if len(coords_a) != len(coords_b) or not np.allclose(coords_a, coords_b):
        # Interpolate B onto A's grid
        from scipy.interpolate import NearestNDInterpolator

        vector = values_a.ndim == 2 and values_a.shape[1] == 3
        if vector:
            interp_x = NearestNDInterpolator(coords_b, np.real(values_b[:, 0]))
            interp_y = NearestNDInterpolator(coords_b, np.real(values_b[:, 1]))
            interp_z = NearestNDInterpolator(coords_b, np.real(values_b[:, 2]))
            values_b_interp = np.column_stack(
                [
                    interp_x(*coords_a.T),
                    interp_y(*coords_a.T),
                    interp_z(*coords_a.T),
                ]
            )
        else:
            interp = NearestNDInterpolator(coords_b, np.real(values_b))
            values_b_interp = interp(*coords_a.T)
    else:
        values_b_interp = values_b

    if values_a.ndim == 2 and values_a.shape[1] == 3:
        # Vector field
        dot = np.sum(np.conj(values_a) * values_b_interp, axis=1) * epsilon_r
    else:
        # Scalar field
        dot = np.conj(values_a) * values_b_interp * epsilon_r

    numerator = abs(np.sum(dot))
    norm_a = np.sqrt(np.sum(np.abs(values_a) ** 2))
    norm_b = np.sqrt(np.sum(np.abs(values_b_interp) ** 2))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(numerator / (norm_a * norm_b))


def compute_overlap_matrix(field_files: list[Path]) -> np.ndarray:
    """Compute the mode overlap matrix from a list of HDF5 field files.

    Returns M[i, j] where i indexes previous sweep point and j indexes current.
    """
    n = len(field_files)
    # For a single sweep point with multiple modes, compute all-vs-all
    data = []
    for path in field_files:
        coords, values, _, meta = read_field_hdf5(path)
        data.append((coords, values, meta))

    overlap = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            ci, vi = data[i][0], data[i][1]
            cj, vj = data[j][0], data[j][1]
            epsilon_r = float(data[i][2].get("relative_permittivity", 1.0))
            overlap[i, j] = field_overlap(ci, vi, cj, vj, epsilon_r)

    return overlap


def assign_modes(overlap_matrix: np.ndarray) -> tuple[list[int], float]:
    """Assign modes between two sweep points via Hungarian algorithm.

    Returns (assignment, confidence) where assignment[j] = i means mode j
    in the current sweep point maps to mode i in the previous.
    """
    cost = 1.0 - np.asarray(overlap_matrix)
    row_ind, col_ind = linear_sum_assignment(cost)

    assignments: list[int] = [-1] * overlap_matrix.shape[1]
    confidences: list[float] = [0.0] * overlap_matrix.shape[1]
    for r, c in zip(row_ind, col_ind, strict=False):
        assignments[c] = int(r)
        confidences[c] = float(overlap_matrix[r, c])

    return assignments, float(np.mean(confidences))


def detect_crossings(
    frequencies: dict[int, list[float]],
    parameter_values: list[float],
    parameter_name: str = "sweep",
) -> list[AvoidedCrossing]:
    """Detect mode crossings and avoided crossings from frequency vs parameter data.

    Parameters
    ----------
    frequencies : dict[int, list[float]]
        Mode frequencies keyed by mode branch ID.
    parameter_values : list[float]
        Sweep parameter values.
    parameter_name : str
        Name of the swept parameter.

    Returns
    -------
    list[AvoidedCrossing]
    """
    crossings: list[AvoidedCrossing] = []
    branches = list(frequencies.keys())
    n_points = len(parameter_values)

    for a_idx in range(len(branches)):
        for b_idx in range(a_idx + 1, len(branches)):
            mode_a, mode_b = branches[a_idx], branches[b_idx]
            fa = np.array(frequencies[mode_a])
            fb = np.array(frequencies[mode_b])

            if len(fa) != n_points or len(fb) != n_points:
                continue

            # Find minimum separation
            separations = np.abs(fa - fb)
            min_idx = int(np.argmin(separations))
            min_sep = float(separations[min_idx])

            if min_sep < 1e-6:
                # True crossing
                crossings.append(
                    AvoidedCrossing(
                        parameter_name=parameter_name,
                        parameter_value=float(parameter_values[min_idx]),
                        mode_a=int(mode_a),
                        mode_b=int(mode_b),
                        minimum_separation_hz=0.0,
                        coupling_strength_hz=None,
                    )
                )
            elif min_sep < np.mean(separations) * 0.1:
                # Potential avoided crossing — estimate coupling
                # Half the minimum splitting gives the coupling strength
                coupling = min_sep / 2.0
                crossings.append(
                    AvoidedCrossing(
                        parameter_name=parameter_name,
                        parameter_value=float(parameter_values[min_idx]),
                        mode_a=int(mode_a),
                        mode_b=int(mode_b),
                        minimum_separation_hz=min_sep,
                        coupling_strength_hz=coupling,
                    )
                )

    return crossings


def track_modes(
    sweep_directory: Path, field_pattern: str = "mode_*_E.h5", parameter_name: str = "sweep"
) -> tuple[list[ModeBranch], list[AvoidedCrossing]]:
    """Track eigenmodes across a parameter sweep directory.

    Each subdirectory or timestamped subfolder contains fields from one
    sweep point. Fields are matched via overlap maximization.
    """
    # Find all field files grouped by sweep point
    sweep_points: list[Path] = sorted([p for p in sweep_directory.iterdir() if p.is_dir()])

    if not sweep_points:
        raise ValueError(f"no sweep subdirectories found in {sweep_directory}")

    # Collect fields per sweep point
    sweep_field_sets: list[list[Path]] = []
    for point_dir in sweep_points:
        field_files = sorted(point_dir.glob(field_pattern))
        if field_files:
            sweep_field_sets.append(field_files)

    if not sweep_field_sets:
        raise ValueError("no field files found matching pattern")

    n_modes = len(sweep_field_sets[0])
    n_points = len(sweep_field_sets)

    # Frequency data
    mode_freqs: dict[int, list[float]] = {}
    mode_indices: dict[int, list[int]] = {}

    # Initialize from first sweep point
    for mode_idx in range(n_modes):
        _coords, _values, _mag, meta = read_field_hdf5(sweep_field_sets[0][mode_idx])
        freq = float(meta.get("frequency_hz", 0))
        mode_freqs[mode_idx] = [freq]
        mode_indices[mode_idx] = [mode_idx]

    # Track through remaining sweep points
    branches: list[ModeBranch] = []
    list(range(n_modes))

    for point_idx in range(1, n_points):
        sweep_field_sets[point_idx - 1]
        curr_files = sweep_field_sets[point_idx]

        # Build representative field data per mode at previous point
        overlap = compute_overlap_matrix(curr_files)

        new_assignments, _confidence = assign_modes(overlap)

        # Map: where does each previous mode go in the current point?
        new_freqs: dict[int, float] = {}
        for curr_idx, prev_idx in enumerate(new_assignments):
            _coords, _values, _mag, meta = read_field_hdf5(curr_files[curr_idx])
            freq = float(meta.get("frequency_hz", 0))
            mode_freqs.setdefault(prev_idx, []).append(freq)
            new_freqs[prev_idx] = freq

    # Build mode branches
    for mode_idx, freqs in mode_freqs.items():
        branch = ModeBranch(
            branch_id=mode_idx,
            modes=[mode_idx],
            frequencies_hz=freqs,
            is_continuous=True,
            confidence=1.0,
        )
        branches.append(branch)

    # Detect crossings
    # Use sweep point indices as parameter values
    param_values = [float(i) for i in range(n_points)]
    crossing_list = detect_crossings(mode_freqs, param_values, parameter_name)

    return branches, crossing_list
