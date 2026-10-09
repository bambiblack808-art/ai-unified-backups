#!/usr/bin/env python3
"""Experimental directional signal for Venture Engine."""

import math
import statistics


def directional_score(prices, eps=1e-12):
    p = [float(x) for x in prices]

    if len(p) < 32:
        return {
            "score": 0.0,
            "direction": "OBSERVE",
            "reason": "INSUFFICIENT_DATA",
        }

    if any(not math.isfinite(x) or x <= 0 for x in p):
        return {
            "score": 0.0,
            "direction": "OBSERVE",
            "reason": "INVALID_PRICES",
        }

    returns = [
        math.log(p[i] / p[i - 1])
        for i in range(1, len(p))
    ]

    recent = returns[-8:]
    baseline = returns[-32:-8]
    baseline_vol = statistics.pstdev(baseline)

    if baseline_vol < eps:
        return {
            "score": 0.0,
            "direction": "OBSERVE",
            "reason": "LOW_BASELINE_VOLATILITY",
        }

    z = statistics.mean(recent) / (
        baseline_vol / math.sqrt(len(recent)) + eps
    )

    score = math.tanh(z / 3.0)

    direction = (
        "UPWARD_BIAS" if score > 0.25
        else "DOWNWARD_BIAS" if score < -0.25
        else "OBSERVE"
    )

    return {
        "score": round(score, 6),
        "direction": direction,
        "reason": "EXPERIMENTAL_RETURN_BASED_SIGNAL",
    }


if __name__ == "__main__":
    rising = [100.0 + i * 0.1 for i in range(40)]
    falling = [104.0 - i * 0.1 for i in range(40)]

    print("Rising test:", directional_score(rising))
    print("Falling test:", directional_score(falling))
    print("Short input:", directional_score([100, 101]))

    print("TEST COMPLETE: research signal only; no orders placed.")
