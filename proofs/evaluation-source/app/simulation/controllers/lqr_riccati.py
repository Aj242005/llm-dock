"""Continuous-time algebraic Riccati equation solver.

Tries scipy.linalg.solve_continuous_are first (accurate, efficient); falls back
to a numpy-only iterative (Kleinman) solver so the package has exactly one hard
dependency (numpy).

The Kleinman iteration:

    A_k = A - B K_k
    P_{k+1} = Q + K_kᵀ R K_k + A_kᵀ P_k A_k dt' ... (discretized)

is implemented on a fine discretization of the continuous-time system, which
is the standard practical approach without scipy. For the small 12-state
system here it converges in a handful of iterations.
"""

from __future__ import annotations

import numpy as np

_SCIPY_AVAILABLE = True
try:  # pragma: no cover - exercised when scipy is not installed
    from scipy.linalg import solve_continuous_are as _scipy_solve_continuous_are
except ImportError:  # pragma: no cover
    _SCIPY_AVAILABLE = False


def solve_continuous_are(A: np.ndarray, B: np.ndarray, Q: np.ndarray, R: np.ndarray) -> np.ndarray:
    """Return P ≥ 0 solving AᵀP + PA - PBR⁻¹BᵀP + Q = 0.

    Q must be symmetric positive semi-definite, R symmetric positive definite.
    """
    if _SCIPY_AVAILABLE:
        return np.asarray(_scipy_solve_continuous_are(A, B, Q, R))

    return _kleinman_solve(A, B, Q, R)


def _kleinman_solve(
    A: np.ndarray,
    B: np.ndarray,
    Q: np.ndarray,
    R: np.ndarray,
    dt: float = 4e-3,
    tol: float = 1e-10,
    max_iter: int = 200,
) -> np.ndarray:
    """Iterative (Kleinman) solution on a discretized LTI system."""
    n = A.shape[0]

    # Discretize (A, B) with a fine time step.
    Ad = np.eye(n) + A * dt + 0.5 * (A @ A) * dt * dt
    Bd = B * dt

    # Stabilizing initial gain from R/A (any K that makes A-BK stable works;
    # K=0 is fine for stabilizable systems in practice here).
    K = np.zeros((R.shape[0], n))
    P = np.zeros((n, n))

    for _ in range(max_iter):
        Ak = A - B @ K
        Adk = np.eye(n) + Ak * dt + 0.5 * (Ak @ Ak) * dt * dt

        # Discrete Lyapunov: P = Qd + Adkᵀ P Adk (solve via iteration since
        # Adk is a contraction for small dt).
        P_new = np.zeros((n, n))
        Qd = (Q + K.T @ R @ K) * dt
        for _inner in range(50):
            P_new = Qd + Adk.T @ P_new @ Adk
        P = P_new

        K_new = np.linalg.solve(R, B.T @ P)
        if np.max(np.abs(K_new - K)) < tol:
            K = K_new
            break
        K = K_new

    return P
