"""Deterministic local datasets, linear surrogates, and inverse design."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class Dataset:
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    provenance: dict[str, str]

    def __post_init__(self) -> None:
        self.x = np.asarray(self.x, dtype=float)
        self.y = np.asarray(self.y, dtype=float)
        if self.x.ndim != 2 or self.y.ndim not in {1, 2} or len(self.x) != len(self.y):
            raise ValueError("x must be 2-D and x/y sample counts must match")
        if not np.all(np.isfinite(self.x)) or not np.all(np.isfinite(self.y)):
            raise ValueError("dataset values must be finite")


@dataclass
class LinearSurrogate:
    coefficients: NDArray[np.float64]

    @classmethod
    def fit(cls, x: NDArray[np.float64], y: NDArray[np.float64]) -> "LinearSurrogate":
        features = np.asarray(x, dtype=float)
        targets = np.asarray(y, dtype=float)
        if features.ndim != 2 or len(features) != len(targets):
            raise ValueError("training arrays are incompatible")
        design = np.column_stack([np.ones(len(features)), features])
        coefficients = np.asarray(np.linalg.lstsq(design, targets, rcond=None)[0], dtype=float)
        return cls(coefficients)

    def predict(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        features = np.asarray(x, dtype=float)
        if features.ndim != 2:
            raise ValueError("prediction features must be 2-D")
        result = np.column_stack([np.ones(len(features)), features]) @ self.coefficients
        return np.asarray(result, dtype=float)

    def inverse_design(
        self,
        candidates: NDArray[np.float64],
        target: NDArray[np.float64] | float,
        *,
        weights: NDArray[np.float64] | None = None,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        predictions = self.predict(candidates)
        residual = predictions - np.asarray(target, dtype=float)
        if residual.ndim == 1:
            score = np.abs(residual)
        else:
            scale = np.ones(residual.shape[1]) if weights is None else np.asarray(weights)
            score = np.sqrt(np.sum((residual * scale) ** 2, axis=1))
        index = int(np.argmin(score))
        return np.asarray(candidates[index], dtype=float), np.asarray(predictions[index])
