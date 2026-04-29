import numpy as np

class Curve:
    """Drop-in replacement for bezier.Curve (cubic only)."""

    def __init__(self, nodes, degree=3):
        self._nodes = np.asarray(nodes, dtype=float)
        if self._nodes.shape != (2, 4):
            raise ValueError("Only 2D cubic Bezier curves (nodes shape (2, 4)) are supported")

    def evaluate_multi(self, s):
        """
        Evaluate the curve at parameter values s.
        s: array-like of values in [0, 1]
        Returns: np.ndarray of shape (2, len(s))
        """
        t = np.asarray(s, dtype=float).reshape(1, -1)
        p0 = self._nodes[:, 0:1]
        p1 = self._nodes[:, 1:2]
        p2 = self._nodes[:, 2:3]
        p3 = self._nodes[:, 3:4]

        one_minus_t = 1.0 - t
        return (
            one_minus_t**3 * p0 +
            3 * one_minus_t**2 * t * p1 +
            3 * one_minus_t * t**2 * p2 +
            t**3 * p3
        )
