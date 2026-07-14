"""Sandbox objective function. Baseline is intentionally suboptimal."""


def score(n: int) -> int:
    """Return a score for integer n.

    Optimal for the template fixtures is n*n (sum of squares).
    Baseline returns 2*n so there is headroom to improve.
    """
    return n * 2  # baseline (suboptimal)
