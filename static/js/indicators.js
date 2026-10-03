// Trailing indicators over valid, chronologically ordered plotted values.
function validatePeriod(period) {
  if (!Number.isInteger(period) || period < 1) throw new RangeError("Use a positive integer window.");
}

export function movingAverage(values, period) {
  validatePeriod(period);
  let sum = 0;
  return values.map((value, index) => {
    sum += value;
    if (index >= period) sum -= values[index - period];
    return index + 1 < period ? null : Math.max(0, sum / period);
  });
}

export function exponentialAverage(values, period) {
  validatePeriod(period);
  const seed = movingAverage(values.slice(0, period), period).at(-1);
  let previous = seed;
  const alpha = 2 / (period + 1);
  return values.map((value, index) => {
    if (index < period - 1) return null;
    if (index >= period) previous = alpha * value + (1 - alpha) * previous;
    return previous;
  });
}

export function rollingMedian(values, period) {
  validatePeriod(period);
  return values.map((value, index) => {
    if (index < period - 1) return null;
    const window = values.slice(index + 1 - period, index + 1).sort((a, b) => a - b);
    const middle = Math.floor(period / 2);
    return period % 2 ? window[middle] : (window[middle - 1] + window[middle]) / 2;
  });
}

export function relativePerformance(values, period = 20) {
  const baseline = movingAverage(values, period);
  return values.map((value, index) => {
    if (index < period || !(baseline[index - 1] > 0)) return null;
    const ratio = value / baseline[index - 1];
    return Number.isFinite(ratio) ? ratio : null;
  });
}
