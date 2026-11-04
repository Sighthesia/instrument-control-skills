#!/usr/bin/env python3
"""Full-record aggregate scanning and the verdict gate for SDS captures.

The scanner never builds an item table: thresholds come from the code
histogram, edges come from one hysteresis state machine whose state is carried
across chunk boundaries, and every reported interval carries display time.

Refusal is a normal return value (``status = "REFUSED"``), never an exception.
"""

from __future__ import annotations

import bisect
import math
from typing import Any, Optional, Sequence

from waveform_analysis import DEFAULT_CHUNK_POINTS, SCHEMA_VERSION, AnalysisError

try:
    import numpy as np
except ImportError:  # pragma: no cover - packaging environment without NumPy
    np = None


# Documented hardware profile the capture context is compared against
# (SKILL.md: 5.00 MSa/s over a 5 s / 25 Mpts record).
TYPICAL_SAMPLE_RATE_HZ = 5.0e6
TYPICAL_RECORD_SPAN_S = 5.0
TYPICAL_CONTEXT_RATIO_RANGE = (0.8, 1.25)

# Histogram occupancy rule: a code bin is occupied when it holds at least
# max(1, total * 1e-6) samples, and a plateau must hold 5% of the record.
OCCUPIED_BIN_FRACTION = 1.0e-6
PLATEAU_MASS_FRACTION = 0.05
# Runs separated by less than max(2, 0.5% of the occupied span) codes are one
# plateau: that gap is code-space dither, not a level boundary.
MERGE_GAP_FRACTION = 0.005
MERGE_GAP_MIN_CODES = 2.0

# Level detection uses histogram mass peaks, not contiguous occupancy runs.
# A fast oscillation spends a large share of its samples in the transitions
# between its two levels: on the reference capture the band between the levels
# holds 49% of the record, so contiguous occupied runs fuse the two levels into
# one 21872-code plateau and the split is never found. Peaks are immune to that
# because a transition is spread thin while a level accumulates mass.
#
# The mass floor is relative to the dominant peak, not to the record. A genuine
# level is a local maximum of comparable mass; transition samples produce small
# local maxima that an absolute floor would accept as levels. On the reference
# capture C1/C2/C3 each carry 5-7 such minor maxima between 0.08% and 0.15% of
# the record, which are 1.5-2.5% of their dominant peak, while their two real
# levels are both above 5% of the record. A 0.10 floor separates the two groups
# cleanly and the result is identical for every floor from 0.05 to 0.30, so the
# choice is not knife-edge.
PEAK_MIN_RELATIVE_MASS = 0.10
PEAK_MIN_ABSOLUTE_SAMPLES = 3
PEAK_MIN_SEPARATION_CODES = 200
PEAK_NEIGHBOURHOOD_CODES = 40
# Thresholds sit symmetrically about the middle of the level gap, so both clear
# their own level's noise band whatever the duty cycle is. The second pair is a
# deliberately tighter re-scan used to detect a pulse split by an intermediate
# level.
THRESHOLD_GAP_OFFSETS = (0.25, 0.75)
SECOND_PAIR_GAP_OFFSETS = (0.40, 0.60)

# A window is "dense" when its local cycle rate is at least half of the fastest
# window; the window-local frequency is the median over that subset.
DENSE_WINDOW_FRACTION_OF_PEAK = 0.5
INTERMITTENT_RATE_RATIO = 2.0
BIMODAL_MEDIAN_MEAN_RATIO = 0.5
# A single-mode half-period population keeps p90 near its median; a record that
# mixes a fast burst with a long quiet stretch pushes p90 far above it.
BIMODAL_P90_RATIO = 4.0


def _require_numpy() -> None:
    if np is None:
        raise AnalysisError("NUMPY_UNAVAILABLE", "NumPy >= 2.0 is required for waveform analysis")
    major = int(np.__version__.split(".", 1)[0])
    if major < 2:
        raise AnalysisError("NUMPY_UNAVAILABLE", f"NumPy >= 2.0 is required; found {np.__version__}")


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _code_domain(width: int) -> tuple[int, int, int]:
    """Return ``(code_min, code_max, representable_limit)`` for the transfer width."""

    if width == 1:
        return -128, 127, 127
    if width == 2:
        return -32768, 32767, 32767
    raise AnalysisError("WIDTH_UNSUPPORTED", f"Unsupported waveform width: {width}")


def _codes_per_div(capture: dict[str, Any]) -> Optional[float]:
    """Codes per division in the capture's OWN transfer domain.

    ``calibration.codes_per_div`` is the BYTE-domain value (30 on this
    firmware), so using it for a WORD frame understates the scale by 256x and
    produces a nonsense clip limit (150 instead of 38400 codes of full scale).

    Three sources are consulted in order, because a capture written before the
    domain annotation existed still carries the old ambiguous preamble and the
    raw evidence must not be rewritten:
      1. the parser's resolved ``code_domain`` plus its per-domain fields,
      2. the legacy ``vertical_code_field`` reinterpreted with the same two-branch
         rule the parser uses, keyed off the transfer width,
      3. the calibration block, as a last resort.
    """

    preamble = capture.get("preamble") or {}
    width = int(capture.get("width") or preamble.get("data_width_bytes") or 0)
    domain = preamble.get("code_domain") or ("word" if width == 2 else "byte" if width == 1 else None)

    if domain == "word":
        # Only the domain-specific field is authoritative here. Falling back to
        # the ambiguous `code_per_div` would reintroduce the 256x error on every
        # capture written before the domain annotation existed.
        value = _finite(preamble.get("codes_per_div_word"))
        if value:
            return value
    elif domain == "byte":
        for key in ("codes_per_div_byte", "code_per_div"):
            value = _finite(preamble.get(key))
            if value:
                return value

    # Legacy preamble: reinterpret the raw descriptor field the way the parser
    # does, so an old WORD capture is not silently scaled by the BYTE value.
    vertical = _finite(preamble.get("vertical_code_field"))
    if vertical is not None:
        if abs(vertical) > 256:
            word_cpd, byte_cpd = vertical, vertical / 256.0
        else:
            byte_cpd, word_cpd = vertical, vertical * 256.0
        if domain == "word":
            return word_cpd
        if domain == "byte":
            return byte_cpd

    return _finite(capture.get("calibration", {}).get("codes_per_div"))


def _clipping_limits(width: int, codes_per_div: Optional[float]) -> dict[str, Any]:
    """Rail limits from the transport width, never from the 5-division screen."""

    _code_min, _code_max, representable = _code_domain(width)
    return {
        "representable_code_limit": representable,
        "full_scale_code": 5.0 * codes_per_div if codes_per_div else None,
        "clip_limit_div": representable / codes_per_div if codes_per_div else None,
    }


def _code_histogram(capture: dict[str, Any], chunk_points: int) -> tuple[Any, int, int]:
    """Exact full-record code histogram, chunked exactly like ``summarize_capture``."""

    samples = capture["samples"]
    code_min, code_max, _limit = _code_domain(int(capture["width"]))
    count = int(capture["points"])
    if len(samples) != count:
        raise AnalysisError("LENGTH_MISMATCH", f"Sample buffer holds {len(samples)} samples; the descriptor declares {count}")
    histogram = np.zeros(code_max - code_min + 1, dtype=np.int64)
    for start in range(0, count, chunk_points):
        block = np.asarray(samples[start : min(start + chunk_points, count)], dtype=np.int64)
        if not block.size:
            continue
        histogram += np.bincount(block - code_min, minlength=histogram.size).astype(np.int64, copy=False)
    return histogram, code_min, count


def _percentile_code(histogram: Any, count: int, percentile: float, code_min: int) -> int:
    rank = max(1, int(math.ceil(percentile * count)))
    index = int(np.searchsorted(np.cumsum(histogram, dtype=np.int64), rank, side="left"))
    return code_min + min(index, histogram.size - 1)


def _median_code(histogram: Any, code_min: int) -> Optional[int]:
    total = int(histogram.sum())
    if total <= 0:
        return None
    return _percentile_code(histogram, total, 0.5, code_min)


def _band_fraction(histogram: Any, code_min: int, low: float, high: float, count: int) -> float:
    """Fraction of samples whose integer code satisfies ``low < code < high``."""

    if count <= 0 or not math.isfinite(low) or not math.isfinite(high) or high <= low:
        return 0.0
    first_code = int(math.floor(low)) + 1
    last_code = int(math.ceil(high)) - 1
    start = max(0, first_code - code_min)
    end = min(histogram.size, last_code - code_min + 1)
    if end <= start:
        return 0.0
    return float(int(histogram[start:end].sum(dtype=np.int64))) / float(count)


def _level_noise_spread(histogram: Any, code_min: int, peak_code: int, count: int, radius: int = 400) -> Optional[float]:
    """Robust half-width of the mass concentrated around one level peak.

    The fraction of samples lying between two thresholds is not a usable
    placement test on an oscillating signal: a fast square wave spends a large
    share of its samples in its own transitions, so a perfectly correct
    threshold pair still reports a large between-threshold fraction (22% on the
    reference capture). What actually matters is whether each threshold sits
    outside the level's own noise band, so this measures that band directly and
    the caller compares the threshold distance against it.
    """

    if count <= 0:
        return None
    start = max(0, peak_code - code_min - radius)
    stop = min(histogram.size, peak_code - code_min + radius + 1)
    if stop <= start:
        return None
    band = histogram[start:stop].astype(np.float64)
    total = band.sum()
    if total <= 0:
        return None
    codes = np.arange(start, stop, dtype=np.float64) + code_min
    weights = band / total
    centre = float((codes * weights).sum())
    variance = float(((codes - centre) ** 2 * weights).sum())
    if variance <= 0:
        return 0.0
    return math.sqrt(variance)


def _thresholds_outside_noise(
    histogram: Any,
    code_min: int,
    count: int,
    low_peak: int,
    high_peak: int,
    low_threshold: float,
    high_threshold: float,
    minimum_sigmas: float,
) -> tuple[bool, dict[str, Any]]:
    """Whether both thresholds clear their level's noise band by ``minimum_sigmas``."""

    low_sigma = _level_noise_spread(histogram, code_min, low_peak, count)
    high_sigma = _level_noise_spread(histogram, code_min, high_peak, count)
    evidence: dict[str, Any] = {
        "low_level_sigma_codes": None if low_sigma is None else round(low_sigma, 3),
        "high_level_sigma_codes": None if high_sigma is None else round(high_sigma, 3),
        "low_threshold_clearance_sigmas": None,
        "high_threshold_clearance_sigmas": None,
        "minimum_sigmas": minimum_sigmas,
    }
    if not low_sigma or not high_sigma:
        # A level with no measurable spread cannot be tested; accept only when a
        # threshold is at least one code away from the peak.
        low_ok = abs(low_threshold - low_peak) >= 1.0
        high_ok = abs(high_peak - high_threshold) >= 1.0
        evidence["noise_band_unmeasurable"] = True
        return low_ok and high_ok, evidence

    low_clearance = (low_threshold - low_peak) / low_sigma
    high_clearance = (high_peak - high_threshold) / high_sigma
    evidence["low_threshold_clearance_sigmas"] = round(low_clearance, 3)
    evidence["high_threshold_clearance_sigmas"] = round(high_clearance, 3)
    return low_clearance >= minimum_sigmas and high_clearance >= minimum_sigmas, evidence


def _snap_to_integer(value: float) -> float:
    """Remove float noise from an exactly integral sample or window index."""

    nearest = round(value)
    if abs(value - nearest) <= 1e-9 * max(1.0, abs(value)):
        return float(nearest)
    return value


def _window_bounds(points: int, interval: float, window_s: float, max_windows: int) -> tuple[int, int, list[tuple[int, int]]]:
    """Sample bounds of the fixed-width window table, plus the uncapped total.

    The record span is rarely an exact multiple of ``window_s``: this capture is
    1.0000000117 s, which divides to 20.0000002 windows. Ceiling that directly
    invents a 21st window of zero width. A span within one part per million of an
    exact multiple is snapped to that multiple instead.
    """

    raw_total = points * interval / window_s
    nearest = round(raw_total)
    if abs(raw_total - nearest) <= 1e-6 * max(1.0, nearest):
        raw_total = float(nearest)
    total_windows = max(1, int(math.ceil(raw_total - 1e-12)))
    window_count = min(total_windows, max_windows)
    bounds: list[tuple[int, int]] = []
    for index in range(window_count):
        start = int(math.ceil(_snap_to_integer(index * window_s / interval)))
        end = int(math.ceil(_snap_to_integer((index + 1) * window_s / interval)))
        start = min(max(start, 0), points)
        end = min(max(end, start), points)
        if index == window_count - 1:
            # The last window absorbs any sub-sample remainder so the table
            # always covers the whole record and never ends with an empty row.
            end = points
        bounds.append((start, end))
    return total_windows, window_count, bounds


def _window_index(index: int, window_starts: Sequence[int], covered_end: int) -> Optional[int]:
    if not window_starts or index >= covered_end:
        return None
    position = bisect.bisect_right(window_starts, index) - 1
    return position if position >= 0 else 0


def _ratio_token(value: float) -> str:
    """Format a ratio for a deviation token without losing magnitude."""

    if value != 0.0 and abs(value) < 0.1:
        return f"{value:.3g}"
    text = f"{value:.2f}"
    if "." in text:
        text = text.rstrip("0")
    if text.endswith("."):
        text += "0"
    return text


def _nanosecond_token(interval_s: float) -> str:
    text = f"{interval_s * 1e9:.6f}"
    if "." in text:
        text = text.rstrip("0")
    if text.endswith("."):
        text = text[:-1]
    return text


def _histogram_peaks(histogram: Any, code_min: int, count: int) -> list[tuple[int, int]]:
    """Significant level peaks as ``(code, mass)`` pairs, left to right.

    A level accumulates mass in a narrow band; the transition between two levels
    spreads its samples thinly across the whole gap, so a level shows up as a
    local maximum that is comparable in mass to the strongest one. The floor is
    therefore relative to the dominant peak: an absolute floor accepts the many
    tiny local maxima the transition band produces.
    """

    if not histogram.size:
        return []
    dominant = int(histogram.max())
    if dominant <= 0:
        return []
    threshold = max(
        float(PEAK_MIN_ABSOLUTE_SAMPLES),
        dominant * PEAK_MIN_RELATIVE_MASS,
    )
    candidates = np.flatnonzero(histogram >= threshold)
    if not candidates.size:
        return []
    span = PEAK_NEIGHBOURHOOD_CODES
    peaks: list[int] = []
    for code in candidates:
        left = max(0, code - span)
        right = min(len(histogram), code + span + 1)
        if histogram[code] >= histogram[left:right].max():
            peaks.append(int(code))
    merged: list[int] = []
    for code in peaks:
        if merged and code - merged[-1] <= PEAK_MIN_SEPARATION_CODES:
            if histogram[code] > histogram[merged[-1]]:
                merged[-1] = code
        else:
            merged.append(code)
    return [(code + code_min, int(histogram[code])) for code in merged]


def _split_code(histogram: Any, code_min: int, low_peak: int, high_peak: int, fraction: float) -> float:
    """Code that splits the mass between two level peaks at ``fraction``.

    Using a mass split rather than the midpoint keeps the thresholds on the
    signal's own levels when the transition band is asymmetric, and it is what
    makes the 25/75 pair differ from the 40/60 re-scan pair.
    """

    start = low_peak - code_min
    stop = high_peak - code_min
    if stop <= start:
        return float(low_peak)
    band = histogram[start:stop + 1]
    total = int(band.sum(dtype=np.int64))
    if total <= 0:
        return float(low_peak + high_peak) / 2.0
    cumulative = np.cumsum(band, dtype=np.int64)
    target = total * fraction
    index = int(np.searchsorted(cumulative, target, side="left"))
    return float(code_min + start + index)


def derive_thresholds(capture: dict[str, Any], *, chunk_points: int = DEFAULT_CHUNK_POINTS) -> dict[str, Any]:
    """Derive a hysteresis threshold pair from the code histogram's level peaks."""

    _require_numpy()
    if chunk_points <= 0:
        raise AnalysisError("LIMIT_INVALID", "chunk_points must be positive")
    histogram, code_min, count = _code_histogram(capture, chunk_points)
    if count <= 0:
        raise AnalysisError("LENGTH_MISMATCH", "Capture record contains no samples")

    peaks = _histogram_peaks(histogram, code_min, count)
    plateaus = [
        {"start_code": code, "end_code": code, "fraction": round(mass / count, 6)}
        for code, mass in peaks
    ]

    percentiles = {
        f"p{int(percentile * 100):02d}": _percentile_code(histogram, count, percentile, code_min)
        for percentile in (0.01, 0.05, 0.5, 0.95, 0.99)
    }

    gap_width: Optional[int] = None
    low_code: Optional[float] = None
    high_code: Optional[float] = None
    second_pair: Optional[list[float]] = None
    near_threshold = 0.0

    if len(peaks) == 2:
        status = "OK"
        low_peak, high_peak = peaks[0][0], peaks[1][0]
        gap_width = high_peak - low_peak
        # Thresholds belong in the middle of the gap, not at a mass quantile.
        # On an oscillating signal the transition samples spread evenly across
        # the whole gap, so a 25% mass split lands right against the low level
        # (0.6 sigma away on the reference capture) and the thresholds sit in
        # that level's own noise band. A symmetric split about the gap centre is
        # the only placement that clears both levels regardless of duty cycle.
        span = float(gap_width)
        low_code = low_peak + THRESHOLD_GAP_OFFSETS[0] * span
        high_code = low_peak + THRESHOLD_GAP_OFFSETS[1] * span
        second_pair = [
            low_peak + SECOND_PAIR_GAP_OFFSETS[0] * span,
            low_peak + SECOND_PAIR_GAP_OFFSETS[1] * span,
        ]
        if high_code <= low_code:
            status = "thresholds_not_separated"
            low_code = high_code = None
            second_pair = None
        else:
            near_threshold = _band_fraction(histogram, code_min, low_code, high_code, count)
    elif len(peaks) == 1:
        status = "thresholds_not_separated"
    elif len(peaks) >= 3:
        status = "multi_level_unresolved"
        widest = max(
            range(len(peaks) - 1),
            key=lambda index: peaks[index + 1][0] - peaks[index][0],
        )
        near_threshold = _band_fraction(
            histogram, code_min, float(peaks[widest][0]), float(peaks[widest + 1][0]), count
        )
    else:
        status = "thresholds_not_separated"

    return {
        "status": status,
        "low_code": low_code,
        "high_code": high_code,
        "second_pair_codes": second_pair,
        "gap_width_codes": gap_width,
        "plateaus": plateaus,
        "percentile_cross_check": percentiles,
        "near_threshold_fraction": near_threshold,
    }


def _histogram_median(histogram: dict[int, int]) -> Optional[float]:
    total = sum(histogram.values())
    if total <= 0:
        return None
    seen = 0
    for value, count in sorted(histogram.items()):
        seen += count
        if seen >= (total + 1) // 2:
            return float(value)
    return None


def scan_hysteresis_aggregates(
    capture: dict[str, Any],
    low_code: float,
    high_code: float,
    *,
    window_s: float = 0.05,
    max_windows: int = 4000,
    chunk_points: int = DEFAULT_CHUNK_POINTS,
) -> dict[str, Any]:
    """One hysteresis state machine over the whole record, accumulating only aggregates."""

    _require_numpy()
    low = _finite(low_code)
    high = _finite(high_code)
    if low is None or high is None or low >= high:
        raise AnalysisError("LIMIT_INVALID", "Thresholds must be finite with low_code < high_code")
    if not math.isfinite(window_s) or window_s <= 0:
        raise AnalysisError("LIMIT_INVALID", "window_s must be a finite positive duration")
    if max_windows <= 0:
        raise AnalysisError("LIMIT_INVALID", "max_windows must be positive")
    if chunk_points <= 1:
        raise AnalysisError("LIMIT_INVALID", "chunk_points must exceed 1")

    samples = capture["samples"]
    points = int(capture["points"])
    if points <= 0:
        raise AnalysisError("LENGTH_MISMATCH", "Capture record contains no samples")
    interval = _finite(capture["sample_interval_s"])
    origin = _finite(capture["time_origin_s"])
    if interval is None or interval <= 0:
        raise AnalysisError("DESCRIPTOR_MISMATCH", "Sample interval must be a positive duration")
    if origin is None:
        raise AnalysisError("DESCRIPTOR_MISMATCH", "Time origin must be a finite display time")
    if window_s < interval:
        raise AnalysisError("LIMIT_INVALID", "window_s is shorter than one sample interval")

    width = int(capture["width"])
    code_min, code_max, representable_limit = _code_domain(width)
    codes_per_div = _codes_per_div(capture)
    limits = _clipping_limits(width, codes_per_div)

    total_windows, window_count, bounds = _window_bounds(points, interval, window_s, max_windows)
    window_starts = [bound[0] for bound in bounds]
    covered_end = bounds[-1][1] if bounds else 0
    high_samples = [0] * window_count
    edge_counts = [0] * window_count
    window_half_periods: list[dict[int, int]] = [{} for _ in range(window_count)]

    # State carried across every chunk boundary: a transition is one physical
    # level change, and a chunk boundary is not a level change. Event codes:
    # 1 rising edge, 0 falling edge, 2/3 first observation of the high/low
    # level (establishes the state but is not a transition).
    state: Optional[str] = None
    previous_transition: Optional[int] = None
    half_periods: dict[int, int] = {}
    edge_count = 0
    minimum = code_max
    maximum = code_min
    total_sum = 0
    rail_samples = 0
    low_histogram = np.zeros(code_max - code_min + 1, dtype=np.int64)
    high_histogram = np.zeros(code_max - code_min + 1, dtype=np.int64)

    for block_start in range(0, points, chunk_points):
        block_end = min(block_start + chunk_points, points)
        values = np.asarray(samples[block_start:block_end], dtype=np.int64)
        if not values.size:
            continue

        total_sum += int(values.sum(dtype=np.int64))
        minimum = min(minimum, int(values.min()))
        maximum = max(maximum, int(values.max()))
        rail_samples += int(np.count_nonzero(np.abs(values) >= representable_limit))
        low_histogram += np.bincount(values[values <= low] - code_min, minlength=low_histogram.size).astype(np.int64, copy=False)
        high_histogram += np.bincount(values[values >= high] - code_min, minlength=high_histogram.size).astype(np.int64, copy=False)

        low_positions = np.flatnonzero(values <= low)
        high_positions = np.flatnonzero(values >= high)
        state_at_chunk_start = state
        size = int(values.size)
        event_offsets = np.empty(size, dtype=np.int64)
        event_states = np.empty(size, dtype=np.int8)
        produced = 0
        cursor = 0
        while cursor < size:
            if state is None:
                low_pick = int(np.searchsorted(low_positions, cursor, side="left"))
                high_pick = int(np.searchsorted(high_positions, cursor, side="left"))
                next_low_offset = int(low_positions[low_pick]) if low_pick < low_positions.size else size
                next_high_offset = int(high_positions[high_pick]) if high_pick < high_positions.size else size
                if next_low_offset == size and next_high_offset == size:
                    break
                if next_low_offset < next_high_offset:
                    state, offset = "low", next_low_offset
                else:
                    state, offset = "high", next_high_offset
                event_code = 3 if state == "low" else 2
            elif state == "low":
                pick = int(np.searchsorted(high_positions, cursor, side="left"))
                if pick >= high_positions.size:
                    break
                offset, state, event_code = int(high_positions[pick]), "high", 1
            else:
                pick = int(np.searchsorted(low_positions, cursor, side="left"))
                if pick >= low_positions.size:
                    break
                offset, state, event_code = int(low_positions[pick]), "low", 0
            event_offsets[produced] = offset
            event_states[produced] = event_code
            produced += 1
            cursor = offset + 1

        offsets = event_offsets[:produced]
        codes = event_states[:produced]
        transitions = offsets[codes <= 1] + block_start
        edge_count += int(transitions.size)

        # High-state coverage as a per-sample prefix sum: a rising edge adds 1
        # from its own sample onwards and a falling edge subtracts 1, so a
        # prefix difference is the exact high-sample count of any slice. The
        # first-observation codes (2/3) only establish the state and carry no
        # delta; `initial_high` supplies the state inherited across the chunk
        # boundary.
        initial_high = 1 if state_at_chunk_start == "high" else 0
        deltas = np.zeros(size, dtype=np.int8)
        rising = (codes == 1) | (codes == 2)
        falling = codes == 0
        deltas[offsets[rising]] = 1
        deltas[offsets[falling]] = -1
        states = np.cumsum(deltas, dtype=np.int64)
        states += initial_high
        prefix = np.zeros(size + 1, dtype=np.int64)
        np.cumsum(states, out=prefix[1:])

        if transitions.size:
            if previous_transition is None:
                gap_values_array = np.diff(transitions)
                gap_anchors = transitions[1:]
            else:
                gap_values_array = np.diff(np.concatenate(([previous_transition], transitions)))
                gap_anchors = transitions
            unique_gaps, gap_counts = np.unique(gap_values_array, return_counts=True)
            for gap_value, gap_count in zip(unique_gaps.tolist(), gap_counts.tolist()):
                half_periods[gap_value] = half_periods.get(gap_value, 0) + gap_count
            if window_count:
                window_starts_array = np.asarray(window_starts, dtype=np.int64)
                edge_window_of = np.searchsorted(window_starts_array, transitions, side="right") - 1
                edge_inside = (edge_window_of >= 0) & (edge_window_of < window_count) & (transitions < covered_end)
                for window_value, window_edges in zip(*np.unique(edge_window_of[edge_inside], return_counts=True)):
                    edge_counts[int(window_value)] += int(window_edges)
                # A half period spans two windows; it is attributed to the
                # window holding the transition that closes it.
                gap_window_of = np.searchsorted(window_starts_array, gap_anchors, side="right") - 1
                gap_inside = (gap_window_of >= 0) & (gap_window_of < window_count) & (gap_anchors < covered_end)
                order = np.argsort(gap_window_of[gap_inside], kind="stable")
                grouped_windows = gap_window_of[gap_inside][order]
                grouped_gaps = gap_values_array[gap_inside][order]
                if grouped_windows.size:
                    boundaries = np.flatnonzero(np.diff(grouped_windows)) + 1
                    for window_chunk, gap_chunk in zip(np.split(grouped_windows, boundaries), np.split(grouped_gaps, boundaries)):
                        local = window_half_periods[int(window_chunk[0])]
                        local_values, local_counts = np.unique(gap_chunk, return_counts=True)
                        for gap_value, gap_count in zip(local_values.tolist(), local_counts.tolist()):
                            local[gap_value] = local.get(gap_value, 0) + gap_count
            previous_transition = int(transitions[-1])

        if window_count:
            first = bisect.bisect_left(window_starts, block_start)
            if first >= window_count:
                first = window_count - 1
            for window in range(first, window_count):
                start, end = bounds[window]
                if start >= block_end:
                    break
                overlap_start = max(start, block_start)
                overlap_end = min(end, block_end)
                if overlap_end > overlap_start:
                    high_samples[window] += int(prefix[overlap_end - block_start] - prefix[overlap_start - block_start])

    mean_code = total_sum / points
    window_rows: list[dict[str, Any]] = []
    window_spans: list[float] = []
    for index, (start, end) in enumerate(bounds):
        t0 = round(origin + start * interval, 12)
        t1 = round(origin + end * interval, 12)
        span = t1 - t0
        window_spans.append(span)
        duty = high_samples[index] / (end - start) if end > start else 0.0
        row: dict[str, Any] = {"t0_s": t0, "t1_s": t1, "duty": round(duty, 6), "edge_count": edge_counts[index]}
        if edge_counts[index] > 0 and span > 0:
            row["cycle_rate_hz"] = round(edge_counts[index] / 2.0 / span, 3)
        window_rows.append(row)

    # Dense windows are the ones whose local cycle rate reaches half of the
    # fastest window; the window-local statistics describe those only, so a
    # bimodal record cannot be summarised by a single record-wide number.
    window_rates = [edge_counts[index] / 2.0 / window_spans[index] if window_spans[index] > 0 else 0.0 for index in range(window_count)]
    dense_indexes: list[int] = []
    peak_rate = max(window_rates) if window_rates else 0.0
    if peak_rate > 0:
        dense_indexes = [index for index, rate in enumerate(window_rates) if rate >= DENSE_WINDOW_FRACTION_OF_PEAK * peak_rate]
    dense_histogram: dict[int, int] = {}
    for index in dense_indexes:
        for samples_in_gap, total in window_half_periods[index].items():
            dense_histogram[samples_in_gap] = dense_histogram.get(samples_in_gap, 0) + total
    # The range is per-window median half periods, the same statistic the
    # headline `dominant_half_period_s` uses, so the two cannot contradict each
    # other; a window-average edge rate is coarser and is published per row.
    dense_frequencies: list[float] = []
    for index in dense_indexes:
        local_median = _histogram_median(window_half_periods[index])
        if local_median:
            dense_frequencies.append(1.0 / (2.0 * local_median * interval))

    half_period_rows = sorted(half_periods.items())
    half_total = sum(total for _samples, total in half_period_rows)
    median_half: Optional[float] = None
    mean_half: Optional[float] = None
    p90_half: Optional[float] = None
    if half_total > 0:
        seen = 0
        median_target = (half_total + 1) // 2
        p90_target = int(math.ceil(0.90 * half_total))
        for samples_in_gap, total in half_period_rows:
            seen += total
            if median_half is None and seen >= median_target:
                median_half = float(samples_in_gap)
            if p90_half is None and seen >= p90_target:
                p90_half = float(samples_in_gap)
                break
        mean_half = sum(samples_in_gap * total for samples_in_gap, total in half_period_rows) / half_total
    dense_median_half = _histogram_median(dense_histogram)

    limitations: list[str] = []
    if total_windows > window_count:
        limitations.append(f"windows_capped_to_{window_count}_of_{total_windows}")

    return {
        "edge_count": edge_count,
        "min_code": minimum,
        "max_code": maximum,
        "mean_code": mean_code,
        "rail_samples": rail_samples,
        "clipped": rail_samples > 0,
        "full_scale_code": limits["full_scale_code"],
        "representable_code_limit": limits["representable_code_limit"],
        "clip_limit_div": limits["clip_limit_div"],
        "low_level_code": _median_code(low_histogram, code_min),
        "high_level_code": _median_code(high_histogram, code_min),
        "half_period_median_samples": median_half,
        "half_period_mean_samples": mean_half,
        "half_period_p90_samples": p90_half,
        "dense_window_median_half_period_samples": dense_median_half,
        "dense_window_frequency_range_hz": [min(dense_frequencies), max(dense_frequencies)] if dense_frequencies else None,
        "windows": window_rows,
        "limitations": limitations,
    }


def _record_extremes(capture: dict[str, Any], chunk_points: int) -> dict[str, Any]:
    """Threshold-free record aggregates, used when the level split is unresolved."""

    samples = capture["samples"]
    points = int(capture["points"])
    width = int(capture["width"])
    code_min, code_max, representable_limit = _code_domain(width)
    minimum = code_max
    maximum = code_min
    total_sum = 0
    rail_samples = 0
    for start in range(0, points, chunk_points):
        block = np.asarray(samples[start : min(start + chunk_points, points)], dtype=np.int64)
        if not block.size:
            continue
        total_sum += int(block.sum(dtype=np.int64))
        minimum = min(minimum, int(block.min()))
        maximum = max(maximum, int(block.max()))
        rail_samples += int(np.count_nonzero(np.abs(block) >= representable_limit))
    limits = _clipping_limits(width, _codes_per_div(capture))
    return {
        "edge_count": None,
        "min_code": minimum,
        "max_code": maximum,
        "mean_code": total_sum / points if points else None,
        "rail_samples": rail_samples,
        "clipped": rail_samples > 0,
        "full_scale_code": limits["full_scale_code"],
        "representable_code_limit": limits["representable_code_limit"],
        "clip_limit_div": limits["clip_limit_div"],
    }


def _context_deviations(capture: dict[str, Any], points: int, interval: float) -> list[str]:
    deviations: list[str] = []
    lower, upper = TYPICAL_CONTEXT_RATIO_RANGE
    rate = _finite(capture.get("sample_rate_hz"))
    if rate is not None and rate > 0:
        ratio = rate / TYPICAL_SAMPLE_RATE_HZ
        if not lower <= ratio <= upper:
            deviations.append(f"sampled_at_{_ratio_token(ratio)}x_typical_sample_rate")
    span = points * interval
    if span > 0:
        ratio = span / TYPICAL_RECORD_SPAN_S
        if not lower <= ratio <= upper:
            deviations.append(f"record_length_{_ratio_token(ratio)}x_typical")
    return deviations


def _refusal_detail(code: str, thresholds: dict[str, Any], near_threshold: float, near_threshold_limit: float) -> str:
    if code == "multi_level_unresolved":
        return f"{len(thresholds['plateaus'])} code plateaus each hold at least 5% of the record; the level structure is unresolved"
    if code == "thresholds_inside_noise":
        return f"{near_threshold:.4%} of samples lie strictly between the thresholds; the limit is {near_threshold_limit:.4%}"
    if code == "no_crossing_observed":
        return "no sample completed a hysteresis crossing across the full record, so no edge structure exists to report"
    if not thresholds["plateaus"]:
        return "no code plateau holds at least 5% of the record; no level separation is observable"
    return (
        f"only {len(thresholds['plateaus'])} code plateau holds at least 5% of the record; "
        "a two-level split requires exactly two separated plateaus"
    )


def build_verdict(
    capture: dict[str, Any],
    *,
    threshold_codes: Optional[Sequence[float]] = None,
    window_s: float = 0.05,
    max_windows: int = 4000,
    near_threshold_limit: float = 0.02,
    minimum_sigmas: float = 3.0,
    chunk_points: int = DEFAULT_CHUNK_POINTS,
) -> dict[str, Any]:
    """Build the verdict document; a refusal is returned, never raised."""

    _require_numpy()
    if not 0.0 <= near_threshold_limit <= 1.0:
        raise AnalysisError("LIMIT_INVALID", "near_threshold_limit must be a fraction in 0..1")
    if minimum_sigmas <= 0:
        raise AnalysisError("LIMIT_INVALID", "minimum_sigmas must be positive")
    if chunk_points <= 0:
        raise AnalysisError("LIMIT_INVALID", "chunk_points must be positive")

    points = int(capture["points"])
    interval = _finite(capture["sample_interval_s"])
    origin = _finite(capture["time_origin_s"])
    if interval is None or interval <= 0:
        raise AnalysisError("DESCRIPTOR_MISMATCH", "Sample interval must be a positive duration")
    if origin is None:
        raise AnalysisError("DESCRIPTOR_MISMATCH", "Time origin must be a finite display time")
    width = int(capture["width"])
    calibration = capture["calibration"]
    scale_status = str(calibration.get("status", "UNKNOWN"))
    codes_per_div = _codes_per_div(capture)
    v_per_div = _finite(calibration.get("effective_vdiv_v_per_div"))
    codes_per_v = codes_per_div / v_per_div if codes_per_div and v_per_div and v_per_div > 0 else None

    limitations: list[str] = []
    thresholds = derive_thresholds(capture, chunk_points=chunk_points)
    # The placement test needs the histogram on both the derived and the explicit
    # threshold paths, so it is built once here rather than inside one branch.
    histogram, code_min, count = _code_histogram(capture, chunk_points)

    explicit: Optional[list[float]] = None
    if threshold_codes is not None:
        explicit = [_finite(value) for value in threshold_codes]
        if len(explicit) != 2 or any(value is None for value in explicit):
            raise AnalysisError("LIMIT_INVALID", "threshold_codes must be exactly two finite codes")
        if explicit[0] >= explicit[1]:
            raise AnalysisError("LIMIT_INVALID", "threshold_codes must be ordered low < high")
        low_code, high_code = float(explicit[0]), float(explicit[1])
        below_end = int(math.floor(low_code)) - code_min + 1
        below = int(histogram[: max(0, min(histogram.size, below_end))].sum(dtype=np.int64))
        above_start = int(math.ceil(high_code)) - code_min
        above = int(histogram[max(0, min(histogram.size, above_start)) :].sum(dtype=np.int64))
        separated = below > 0 and above > 0
        near_threshold = _band_fraction(histogram, code_min, low_code, high_code, count)
    else:
        low_code = thresholds["low_code"]
        high_code = thresholds["high_code"]
        separated = thresholds["status"] == "OK" and low_code is not None and high_code is not None
        near_threshold = float(thresholds["near_threshold_fraction"])
    reported_codes = [float(low_code), float(high_code)] if low_code is not None and high_code is not None else None

    # Threshold placement is judged against each level's own noise band, not
    # against the between-threshold sample fraction: an oscillating signal
    # legitimately fills that band with its transitions (22% on the reference
    # capture) while its thresholds are perfectly placed.
    placement_ok = True
    placement_evidence: dict[str, Any] = {}
    if separated and reported_codes is not None and thresholds.get("plateaus"):
        peaks = [entry["start_code"] for entry in thresholds["plateaus"]]
        if len(peaks) >= 2:
            placement_ok, placement_evidence = _thresholds_outside_noise(
                histogram,
                code_min,
                count,
                peaks[0],
                peaks[-1],
                reported_codes[0],
                reported_codes[1],
                minimum_sigmas,
            )

    scan: Optional[dict[str, Any]] = None
    if separated:
        scan = scan_hysteresis_aggregates(
            capture,
            float(low_code),
            float(high_code),
            window_s=window_s,
            max_windows=max_windows,
            chunk_points=chunk_points,
        )
        envelope: dict[str, Any] = scan
        limitations.extend(scan["limitations"])
    else:
        envelope = _record_extremes(capture, chunk_points)
        limitations.append("record_structure_not_scanned_thresholds_not_separated")

    refusal_code: Optional[str] = None
    if not separated:
        refusal_code = "thresholds_not_separated" if explicit is not None else str(thresholds["status"])
    elif not placement_ok:
        refusal_code = "thresholds_inside_noise"
    elif scan is not None and scan["edge_count"] == 0:
        refusal_code = "no_crossing_observed"
    refusal_detail = _refusal_detail(refusal_code, thresholds, near_threshold, near_threshold_limit) if refusal_code else None

    if scale_status != "VALID":
        limitations.append("absolute_voltage_fields_withheld_scale_not_valid")

    frame_evidence = (
        "existing_stopped_no_ready_to_stop"
        if capture["manifest"].get("existing_stop_claims_new_transition") is False
        else "observed_ready_to_stop"
    )
    provenance = {
        "frame_evidence": frame_evidence,
        "context_deviations": _context_deviations(capture, points, interval),
    }

    domain_block = {
        "code_domain": "word" if width == 2 else "byte",
        "codes_per_div": codes_per_div,
        "v_per_div": v_per_div,
        "codes_per_v": codes_per_v,
        "scale_status": scale_status,
        "scale_source": calibration.get("source"),
    }

    low_v: Optional[float] = None
    high_v: Optional[float] = None
    if scale_status == "VALID" and separated:
        scale = _finite(calibration.get("code_scale_v"))
        offset = _finite(calibration.get("effective_offset_v"))
        if scale is not None and offset is not None:
            low_v = float(low_code) * scale - offset
            high_v = float(high_code) * scale - offset
    levels_block = {
        "low_v": low_v,
        "high_v": high_v,
        "threshold_codes": reported_codes,
        "threshold_evidence": {
            "p01": thresholds["percentile_cross_check"]["p01"],
            "p05": thresholds["percentile_cross_check"]["p05"],
            "p50": thresholds["percentile_cross_check"]["p50"],
            "p95": thresholds["percentile_cross_check"]["p95"],
            "p99": thresholds["percentile_cross_check"]["p99"],
            "near_threshold_fraction": near_threshold,
            "near_threshold_fraction_note": "diagnostic only; a fast oscillation fills this band with its own transitions, so it is not a placement test",
            "placement": placement_evidence,
            "plateaus": thresholds["plateaus"],
        },
    }

    structure_block = {
        # A refusal never asserts the full-resolution state scan it did not run.
        "scan": "full_record_original_resolution" if scan is not None else "record_extremes_only_thresholds_not_separated",
        "edge_count": envelope["edge_count"],
        "detection_resolution_s": interval,
        "rail_samples": envelope["rail_samples"],
        "clipped": envelope["clipped"],
        "min_code": envelope["min_code"],
        "max_code": envelope["max_code"],
        "full_scale_code": envelope["full_scale_code"],
        "representable_code_limit": envelope["representable_code_limit"],
        "clip_limit_div": envelope["clip_limit_div"],
        "clipping_detectable_up_to_div": envelope["clip_limit_div"],
    }

    windows = scan["windows"] if scan is not None else []
    median_half_samples = scan["half_period_median_samples"] if scan is not None else None
    mean_half_samples = scan["half_period_mean_samples"] if scan is not None else None
    dense_half_samples = scan["dense_window_median_half_period_samples"] if scan is not None else None
    dense_window_rates = scan["dense_window_frequency_range_hz"] if scan is not None else None
    dominant_half_period_s = dense_half_samples * interval if dense_half_samples else None
    dense_local_frequency = 1.0 / (2.0 * dominant_half_period_s) if dominant_half_period_s else None
    full_record_mean_half_period_s = mean_half_samples * interval if mean_half_samples else None
    full_record_mean_frequency_hz = 1.0 / (2.0 * full_record_mean_half_period_s) if full_record_mean_half_period_s else None
    bimodal = bool(
        median_half_samples
        and mean_half_samples
        and abs(mean_half_samples - median_half_samples) / median_half_samples > BIMODAL_MEDIAN_MEAN_RATIO
    )
    if not bimodal and scan is not None:
        # The median/mean test misses a record that is half fast oscillation and
        # half silence: the mean is dragged up but can stay within 50% of the
        # median. A spread test on the half-period population catches it, because
        # a single-mode population keeps its p90 close to its median.
        p90 = scan.get("half_period_p90_samples")
        if median_half_samples and p90 and p90 > median_half_samples * BIMODAL_P90_RATIO:
            bimodal = True
    if scan is None:
        distribution_note = "not_computed: the record structure was not scanned because the level split is unresolved"
    elif bimodal:
        distribution_note = (
            f"bimodal: median half period {median_half_samples:g} samples and mean half period "
            f"{mean_half_samples:.3f} samples differ by more than 50%; neither statistic describes the whole record"
        )
    elif median_half_samples:
        distribution_note = "median and mean half period agree within 50%; the half-period population is not bimodal"
    else:
        distribution_note = "no repeating structure was detected, so no half-period distribution exists"

    timing_block = {
        "dominant_half_period_s": dominant_half_period_s,
        "basis": "median_half_period_within_dense_windows",
        "dense_window_local_frequency_hz": dense_local_frequency,
        "dense_window_frequency_range_hz": dense_window_rates,
        "full_record_mean_half_period_s": full_record_mean_half_period_s,
        "full_record_mean_frequency_hz": full_record_mean_frequency_hz,
        "distribution_note": distribution_note,
    }

    samples_per_cycle = int(round(2 * dense_half_samples)) if dense_half_samples else None
    if dense_local_frequency and dense_local_frequency > 0:
        nyquist = 0.5 / interval
        highest_harmonic = int(math.floor(nyquist / dense_local_frequency))
        if highest_harmonic >= 1:
            harmonic_visibility = (
                f"fundamental_resolved; harmonics above the {highest_harmonic}th alias at "
                f"{1.0 / interval / 1e6:.6g} MSa/s"
            )
        else:
            harmonic_visibility = "fundamental_not_resolved_above_nyquist"
        sampling_note = (
            "half periods are integer sample counts, so a non-integer period appears as adjacent counts; "
            "sub-sample period jitter is not measurable"
        )
    else:
        harmonic_visibility = "no_repeating_structure_resolved"
        sampling_note = "no repeating structure was resolved, so sampling risk is not characterised"
    sampling_risk_block = {
        "samples_per_cycle_at_dense_frequency": samples_per_cycle,
        "period_quantisation_s": interval,
        "period_quantisation_fraction_of_half_period": 1.0 / dense_half_samples if dense_half_samples else None,
        "harmonic_visibility": harmonic_visibility,
        "note": sampling_note,
    }

    intermittent = bool(
        dense_local_frequency and full_record_mean_frequency_hz and dense_local_frequency >= INTERMITTENT_RATE_RATIO * full_record_mean_frequency_hz
    )
    can_claim: list[str] = []
    if refusal_code is None:
        can_claim.append("levels")
        if dense_local_frequency:
            can_claim.append("dense_window_local_frequency")
        if intermittent:
            can_claim.append("intermittent_burst_structure")
        if not envelope["clipped"]:
            can_claim.append("no_clipping")
    cannot_claim: list[str] = []
    if scale_status != "VALID":
        cannot_claim.append("absolute_voltage_accuracy")
    cannot_claim.extend(["period_stability_beyond_sample_grid", "stability_and_transition_analysis", "multi_channel_causality"])
    if bimodal:
        cannot_claim.append("single_continuous_frequency")
    must_state: list[str] = []
    if frame_evidence == "existing_stopped_no_ready_to_stop":
        must_state.append("existing_stopped_no_ready_to_stop")
    if scale_status != "VALID":
        must_state.append("scale_observed_unverified_internal_consistency_only")
    must_state.append(f"detection_resolution_{_nanosecond_token(interval)}ns")
    if dense_local_frequency:
        must_state.append("frequency_basis_is_window_local_not_record_wide")
    must_state.append("single_channel_analysis_only")

    verdict: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tool": "verdict",
        "status": "OBSERVED" if refusal_code is None else "REFUSED",
        "limitations": limitations,
        "capture": {
            "channel": capture.get("channel"),
            "points": points,
            "merged_sha256": capture.get("raw_sha256"),
            "interval_s": interval,
            "origin_s": origin,
            "time_reference": "display",
        },
        "integrity": {
            "status": capture["integrity"].get("status"),
            "segments_verified": capture["integrity"].get("segments_verified"),
        },
        "provenance": provenance,
        "domain": domain_block,
        "levels": levels_block,
        "structure": structure_block,
        "sampling_risk": sampling_risk_block,
        "timing": timing_block,
        "windows": windows,
        "claims": {"can_claim": can_claim, "cannot_claim": cannot_claim, "must_state": must_state},
    }
    if refusal_code is not None:
        verdict["refusal"] = {"code": refusal_code, "detail": refusal_detail}
    return verdict
