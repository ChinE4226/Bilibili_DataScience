"""Trailing indicators over valid plotted values, without file or network access."""
from statistics import median
import math


def _validate_period(period: int) -> None:
    if type(period) is not int or period < 1:
        raise ValueError("Use a positive integer window.")


def moving_average(values: list[float], period: int) -> list[float | None]:
    _validate_period(period)
    result = []
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= period:
            total -= values[index - period]
        result.append(None if index + 1 < period else max(0.0, total / period))
    return result


def exponential_average(values: list[float], period: int) -> list[float | None]:
    _validate_period(period)
    if len(values) < period:
        return [None] * len(values)
    previous = sum(values[:period]) / period
    result = [None] * (period - 1) + [previous]
    alpha = 2 / (period + 1)
    for value in values[period:]:
        previous = alpha * value + (1 - alpha) * previous
        result.append(previous)
    return result


def rolling_median(values: list[float], period: int) -> list[float | None]:
    _validate_period(period)
    return [None if index < period - 1 else median(values[index + 1 - period:index + 1])
            for index in range(len(values))]


def relative_performance(values: list[float], period: int = 20) -> list[float | None]:
    baseline = moving_average(values, period)
    result = []
    for index, value in enumerate(values):
        ratio = value / baseline[index - 1] if index >= period and baseline[index - 1] > 0 else None
        result.append(ratio if ratio is not None and math.isfinite(ratio) else None)
    return result
