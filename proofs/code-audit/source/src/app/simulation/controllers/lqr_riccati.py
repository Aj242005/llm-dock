"""Use SciPy's standard Riccati solver for the LQR gain."""

from scipy.linalg import solve_continuous_are

__all__ = ["solve_continuous_are"]
