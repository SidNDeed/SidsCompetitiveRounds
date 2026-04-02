"""
Glicko-2 Rating System Implementation
Based on Mark Glickman's paper: http://www.glicko.net/glicko/glicko2.pdf

This module handles all rating calculations for Competitive ROUNDS.
"""

import math
from dataclasses import dataclass


# Glicko-2 uses an internal scale factor
SCALE = 173.7178


@dataclass
class Rating:
    """A player's Glicko-2 rating state."""
    mu: float        # rating on Glicko-2 scale
    phi: float       # rating deviation on Glicko-2 scale
    sigma: float     # volatility


@dataclass
class Opponent:
    """An opponent faced during a rating period."""
    mu: float
    phi: float
    score: float     # 1.0 = win, 0.0 = loss, 0.5 = draw


def rating_to_glicko2(rating: float, rd: float) -> tuple[float, float]:
    """Convert Glicko-1 scale (1500 center) to Glicko-2 internal scale."""
    mu = (rating - 1500.0) / SCALE
    phi = rd / SCALE
    return mu, phi


def glicko2_to_rating(mu: float, phi: float) -> tuple[float, float]:
    """Convert Glicko-2 internal scale back to Glicko-1 display scale."""
    rating = mu * SCALE + 1500.0
    rd = phi * SCALE
    return rating, rd


def _g(phi: float) -> float:
    """Compute the g function that reduces impact of uncertain opponents."""
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _E(mu: float, mu_j: float, phi_j: float) -> float:
    """Expected score against an opponent (logistic function)."""
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _compute_variance(mu: float, opponents: list[Opponent]) -> float:
    """
    Step 3: Compute the estimated variance of the player's rating
    based on game outcomes.
    """
    v_inv = 0.0
    for opp in opponents:
        g_phi = _g(opp.phi)
        e = _E(mu, opp.mu, opp.phi)
        v_inv += g_phi * g_phi * e * (1.0 - e)
    return 1.0 / v_inv if v_inv > 0 else float("inf")


def _compute_delta(mu: float, opponents: list[Opponent], v: float) -> float:
    """
    Step 4: Compute the estimated improvement in rating.
    """
    total = 0.0
    for opp in opponents:
        g_phi = _g(opp.phi)
        e = _E(mu, opp.mu, opp.phi)
        total += g_phi * (opp.score - e)
    return v * total


def _new_volatility(sigma: float, phi: float, v: float, delta: float, tau: float) -> float:
    """
    Step 5: Determine new volatility using the iterative algorithm
    (Illinois method as described in the Glicko-2 paper).
    """
    a = math.log(sigma * sigma)
    epsilon = 0.000001

    def f(x: float) -> float:
        ex = math.exp(x)
        d2 = delta * delta
        phi2 = phi * phi
        top = ex * (d2 - phi2 - v - ex)
        bottom = 2.0 * (phi2 + v + ex) ** 2
        return top / bottom - (x - a) / (tau * tau)

    # Set initial bounds
    A = a
    if delta * delta > phi * phi + v:
        B = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        B = a - k * tau

    # Iterate
    f_A = f(A)
    f_B = f(B)
    while abs(B - A) > epsilon:
        C = A + (A - B) * f_A / (f_B - f_A)
        f_C = f(C)
        if f_C * f_B <= 0:
            A = B
            f_A = f_B
        else:
            f_A = f_A / 2.0
        B = C
        f_B = f_C

    return math.exp(A / 2.0)


def calculate_new_rating(
    rating: float,
    rd: float,
    volatility: float,
    opponents: list[tuple[float, float, float]],
    tau: float = 0.5,
) -> tuple[float, float, float]:
    """
    Calculate a player's new Glicko-2 rating after a rating period.

    Args:
        rating: Current rating (Glicko-1 scale, e.g. 1500)
        rd: Current rating deviation (Glicko-1 scale, e.g. 350)
        volatility: Current volatility (e.g. 0.06)
        opponents: List of (opponent_rating, opponent_rd, score) tuples
                   where score is 1.0=win, 0.0=loss, 0.5=draw
        tau: System constant controlling volatility change (0.3 to 1.2)

    Returns:
        Tuple of (new_rating, new_rd, new_volatility) on Glicko-1 scale.
    """
    # Step 1: Convert to Glicko-2 scale
    mu, phi = rating_to_glicko2(rating, rd)

    # If no games played, only RD increases (Step 6 shortcut)
    if not opponents:
        phi_star = math.sqrt(phi * phi + volatility * volatility)
        new_rating, new_rd = glicko2_to_rating(mu, phi_star)
        return new_rating, new_rd, volatility

    # Convert opponent data
    opps = []
    for opp_rating, opp_rd, score in opponents:
        opp_mu, opp_phi = rating_to_glicko2(opp_rating, opp_rd)
        opps.append(Opponent(mu=opp_mu, phi=opp_phi, score=score))

    # Step 3: Compute variance
    v = _compute_variance(mu, opps)

    # Step 4: Compute improvement
    delta = _compute_delta(mu, opps, v)

    # Step 5: Determine new volatility
    new_sigma = _new_volatility(volatility, phi, v, delta, tau)

    # Step 6: Update RD to new pre-rating period value
    phi_star = math.sqrt(phi * phi + new_sigma * new_sigma)

    # Step 7: Update rating and RD
    new_phi = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)

    update_sum = 0.0
    for opp in opps:
        g_phi = _g(opp.phi)
        e = _E(mu, opp.mu, opp.phi)
        update_sum += g_phi * (opp.score - e)

    new_mu = mu + new_phi * new_phi * update_sum

    # Convert back to Glicko-1 scale
    new_rating, new_rd = glicko2_to_rating(new_mu, new_phi)

    return new_rating, new_rd, new_sigma
