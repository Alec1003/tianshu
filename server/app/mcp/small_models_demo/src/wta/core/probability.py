"""二项分布概率函数 — 用于 MILP 中置信命中层级的预计算。"""

from __future__ import annotations

import math


def binomial_tail_probability(
    trials: int, required_hits: int, probability: float
) -> float:
    """计算 P(X >= required_hits) 在 Binomial(trials, probability) 下的尾部概率。"""
    if required_hits <= 0:
        return 1.0
    if required_hits > trials:
        return 0.0
    q = 1.0 - probability
    cumulative = 0.0
    for hits in range(required_hits, trials + 1):
        cumulative += (
            math.comb(trials, hits) * (probability**hits) * (q ** (trials - hits))
        )
    return cumulative


def min_launches_for_confident_hits(
    required_hits: int, probability: float, confidence: float, max_trials: int
) -> int:
    """二分搜索：找到满足置信度要求的最少发射数。"""
    if required_hits <= 0:
        return 0
    for trials in range(required_hits, max_trials + 1):
        if binomial_tail_probability(trials, required_hits, probability) >= confidence:
            return trials
    raise ValueError(
        f"Unable to satisfy confident-hit requirement {required_hits} "
        f"with max_trials={max_trials}, p={probability}, c={confidence}"
    )


def max_confident_hits_for_launch_cap(
    max_trials: int, probability: float, confidence: float
) -> int:
    """给定发射上限，找出在置信度 c 下最多能保证多少发命中。"""
    max_hits = 0
    for hits in range(1, max_trials + 1):
        if binomial_tail_probability(max_trials, hits, probability) >= confidence:
            max_hits = hits
        else:
            break
    return max_hits
