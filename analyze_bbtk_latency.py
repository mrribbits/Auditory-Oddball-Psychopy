#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BBTK Audio Latency Analysis
========================================================================

Parses BBTK RTL (raw event log) files, extracts trigger-to-mic
latencies for each trial, computes summary statistics, and generates
visualizations comparing multiple recording conditions.

Typical use: compare VPIXX audio vs. PsychoPy PTB audio through the
same pneumatic-tube pathway, and (optionally) compare either against
room-loudspeaker output to isolate the tube contribution.


RTL FILE FORMAT (as observed in BBTKv2ELITE exports)
----------------------------------------------------
Header lines: [Key] tags followed by values on the next line.
Data section: `[Data]` marker, then one 32-character line per
              signal-state change:
                  chars 1-23  : signal state (one bit per channel)
                  chars 24-32 : timestamp in microseconds, zero-padded

Bit positions (empirically observed, 1-indexed left-to-right in the
signal state string):
    position 10 : TTL In 1  -> pixel trigger from VPIXX DOUT
    position 12 : Audio In 1 -> earpiece / room microphone

Each trial produces 4 events (in this order): trigger rising, mic
rising, trigger falling, mic falling. The latency of interest is
(mic rising) - (trigger rising) per trial.


CONFIGURATION
-------------
Edit INPUT_FILES at the top of the script to point to your RTL files
with descriptive labels. The script auto-detects which files are
"tubes" vs. "speakers" and "VPIXX" vs. "PsychoPy" for derived
comparisons.


OUTPUTS
-------
- Console:
    - Per-condition summary (N, mean, SD, median, IQR)
    - Derived comparisons (tube transit time, PsychoPy overhead)
- Figure saved to `analysis_figures/audio_latency_analysis.png`:
    - Row 1: per-condition histograms with mean/median markers
    - Row 2: overlaid histograms for direct comparison
    - Row 3: per-trial scatter (drift / stability check)
"""

import os
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec


# =============================================================================
# CONFIGURATION - edit these to point to your RTL files
# =============================================================================

INPUT_FILES = {
    'VPIXX / earpiece tubes':    'audio-latency-eartubes-vpixx.rtl',
    'PsychoPy / earpiece tubes': 'audio-latency-eartubes-psychopy.rtl',
    'VPIXX / room speakers':     'audio-latency-speakers-vpixx.rtl',
}

# Output figures directory
FIGURES_DIR = 'analysis_figures'

# --- Optional speaker-to-mic distance correction ---
#
# The raw "tubes - speakers" difference is biased downward by however
# many ms of acoustic travel exists in the SPEAKERS condition (from
# speaker to mic through open air). That travel is not present in the
# tubes condition (mic is right at the earpiece), so subtracting the
# raw speakers-baseline leaves the "true tube transit" underestimated
# by the speaker-to-mic air transit.
#
# If you know the speaker-to-mic distance, set it here in meters and
# the analyzer will estimate that transit and remove it from the
# speakers baseline before computing the tube-transit derived value.
#
# Set to None (default) to skip the correction and show the raw diff.
#
# Common distances (for reference):
#     1 ft  = 0.30 m       6 ft  = 1.83 m
#     3 ft  = 0.91 m      10 ft  = 3.05 m
SPEAKER_TO_MIC_DISTANCE_M = None    # e.g. 1.83 for 6 feet

# Speed of sound in air at room temperature (~20 C). Fine for lab use;
# doesn't vary enough with temperature to change the ms-level results.
SPEED_OF_SOUND_M_PER_S = 343.0


# =============================================================================
# RTL FORMAT CONSTANTS
# =============================================================================

STATE_WIDTH     = 23   # channel-state bits at start of each data line
TIMESTAMP_WIDTH = 9    # μs timestamp at end of each data line (zero-padded)

# Bit positions (0-indexed, left-to-right in the state string)
TRIGGER_BIT_INDEX = 9    # position 10 = TTL In 1 = pixel trigger
MIC_BIT_INDEX     = 11   # position 12 = Audio In 1 = mic

# Max plausible trigger->mic delay in μs. Anything larger is treated
# as a missed pair (mic didn't detect this trial's tone; skip it).
MAX_LATENCY_US = 500_000   # 500 ms


# =============================================================================
# RTL PARSING
# =============================================================================

def parse_rtl(filepath):
    """Parse a BBTK RTL file.

    Returns
    -------
    events : list of dict
        One dict per state-change event, with keys:
            t_us         : timestamp in microseconds (int)
            state        : full 23-char signal state string
            trigger_high : bool, is pixel_trigger currently high
            mic_high     : bool, is mic currently high
    header : dict
        Key/value pairs from the file header.
    """
    events = []
    header = {}

    with open(filepath, 'r') as f:
        lines = f.readlines()

    in_data     = False
    current_key = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if line == '[Data]':
            in_data = True
            continue

        if in_data:
            # Data line: STATE_WIDTH chars of bits + TIMESTAMP_WIDTH chars of μs
            if len(line) != STATE_WIDTH + TIMESTAMP_WIDTH:
                continue  # skip malformed lines silently
            state = line[:STATE_WIDTH]
            t_str = line[STATE_WIDTH:]
            try:
                t_us = int(t_str)
            except ValueError:
                continue
            events.append({
                't_us':         t_us,
                'state':        state,
                'trigger_high': state[TRIGGER_BIT_INDEX] == '1',
                'mic_high':     state[MIC_BIT_INDEX] == '1',
            })
        else:
            # Header: [Key] on one line, value on the next
            if line.startswith('[') and line.endswith(']'):
                current_key = line[1:-1]
            elif current_key is not None:
                header[current_key] = line
                current_key = None

    return events, header


def extract_trigger_mic_pairs(events):
    """Pair each trigger rising edge with the next mic rising edge.

    Trials where no mic rising edge occurs within MAX_LATENCY_US of a
    trigger are dropped (with the trigger not consumed, in case the
    next trigger is close by -- but with 200-trial data this rarely
    matters). Returns two same-length arrays of matched timestamps.
    """
    trigger_rising = []
    mic_rising     = []

    prev_trigger = False
    prev_mic     = False
    for ev in events:
        if ev['trigger_high'] and not prev_trigger:
            trigger_rising.append(ev['t_us'])
        if ev['mic_high'] and not prev_mic:
            mic_rising.append(ev['t_us'])
        prev_trigger = ev['trigger_high']
        prev_mic     = ev['mic_high']

    trigger_rising = np.array(trigger_rising, dtype=np.int64)
    mic_rising     = np.array(mic_rising, dtype=np.int64)

    # For each trigger, find the first mic rising edge after it and
    # within the max-latency window.
    paired_trigger = []
    paired_mic     = []
    mic_idx        = 0
    dropped        = 0

    for t_trig in trigger_rising:
        # Advance mic_idx past any mic edges that occurred BEFORE this trigger
        while mic_idx < len(mic_rising) and mic_rising[mic_idx] < t_trig:
            mic_idx += 1
        if mic_idx >= len(mic_rising):
            dropped += 1
            break
        delta = mic_rising[mic_idx] - t_trig
        if delta <= MAX_LATENCY_US:
            paired_trigger.append(t_trig)
            paired_mic.append(mic_rising[mic_idx])
            mic_idx += 1   # consume this mic edge
        else:
            dropped += 1
            # Do NOT consume mic_idx -- leave for potential next trigger

    return (np.array(paired_trigger, dtype=np.int64),
            np.array(paired_mic,     dtype=np.int64),
            dropped)


def compute_latencies(events):
    """Return per-trial trigger->mic latencies in milliseconds."""
    trig_t, mic_t, dropped = extract_trigger_mic_pairs(events)
    latencies_us = mic_t - trig_t
    return latencies_us / 1000.0, dropped


# =============================================================================
# STATS
# =============================================================================

def summarize(latencies_ms, label=''):
    """Return summary statistics as a dict."""
    if len(latencies_ms) == 0:
        return {'label': label, 'n': 0}
    return {
        'label':  label,
        'n':      int(len(latencies_ms)),
        'mean':   float(np.mean(latencies_ms)),
        'std':    float(np.std(latencies_ms, ddof=1)),
        'median': float(np.median(latencies_ms)),
        'p25':    float(np.percentile(latencies_ms, 25)),
        'p75':    float(np.percentile(latencies_ms, 75)),
        'iqr':    float(np.percentile(latencies_ms, 75)
                        - np.percentile(latencies_ms, 25)),
        'min':    float(np.min(latencies_ms)),
        'max':    float(np.max(latencies_ms)),
    }


def print_summary_table(all_data):
    """Print a per-condition summary table."""
    print()
    print("=" * 82)
    print("LATENCY SUMMARY (ms)")
    print("=" * 82)
    print(f"{'Condition':<32} {'N':>5} {'Mean':>8} {'SD':>8} "
          f"{'Median':>8} {'IQR':>8} {'Min':>7} {'Max':>7}")
    print("-" * 82)
    for label, d in all_data.items():
        s = d['stats']
        if s['n'] == 0:
            print(f"{label:<32} {'(no data)':>10}")
            continue
        print(f"{label:<32} {s['n']:>5} "
              f"{s['mean']:>8.2f} {s['std']:>8.2f} "
              f"{s['median']:>8.2f} {s['iqr']:>8.2f} "
              f"{s['min']:>7.2f} {s['max']:>7.2f}")
    print("=" * 82)


def print_derived_comparisons(all_data):
    """Print tube-transit-time and PsychoPy-overhead comparisons.

    Auto-detects condition roles from the label text:
        contains 'vpixx' + 'tube'     -> vpixx_tubes
        contains 'psychopy' + 'tube'  -> psychopy_tubes
        contains 'vpixx' + 'speaker'  -> vpixx_speakers
    """
    def find(patterns):
        for label in all_data:
            if all(p in label.lower() for p in patterns):
                return label
        return None

    vpixx_tubes    = find(['vpixx', 'tube'])
    psychopy_tubes = find(['psychopy', 'tube'])
    vpixx_speakers = find(['vpixx', 'speaker'])

    print()
    print("DERIVED COMPARISONS (ms)")
    print("=" * 82)

    if vpixx_tubes and vpixx_speakers:
        mt = all_data[vpixx_tubes]['stats']['mean']
        ms = all_data[vpixx_speakers]['stats']['mean']
        st = all_data[vpixx_tubes]['stats']['std']
        ss = all_data[vpixx_speakers]['stats']['std']
        diff = mt - ms
        # Sum-of-variances for the SD of the difference
        sd_diff = np.sqrt(st**2 + ss**2)
        print(f"Tube transit time  (VPIXX/tubes - VPIXX/speakers):")
        print(f"    = {mt:.2f} - {ms:.2f}")
        print(f"    = {diff:.2f} ms  (combined SD: {sd_diff:.2f} ms)")
        print(f"    Interpretation: acoustic transit through the tubing,")
        print(f"    biased LOW by the speaker-to-mic air transit that is")
        print(f"    included in the speakers baseline but not in the tubes")
        print(f"    condition. Set SPEAKER_TO_MIC_DISTANCE_M to correct.")

        if SPEAKER_TO_MIC_DISTANCE_M is not None:
            speaker_air_ms = (SPEAKER_TO_MIC_DISTANCE_M
                              / SPEED_OF_SOUND_M_PER_S) * 1000.0
            ms_corrected  = ms - speaker_air_ms
            diff_corrected = mt - ms_corrected
            dist_ft = SPEAKER_TO_MIC_DISTANCE_M / 0.3048
            print()
            print(f"    -- With speaker-to-mic distance correction --")
            print(f"    Speaker-to-mic distance: "
                  f"{SPEAKER_TO_MIC_DISTANCE_M:.2f} m ({dist_ft:.2f} ft)")
            print(f"    Speaker-to-mic air transit: "
                  f"{speaker_air_ms:.2f} ms  @ {SPEED_OF_SOUND_M_PER_S} m/s")
            print(f"    Corrected tube transit time:")
            print(f"        = {mt:.2f} - ({ms:.2f} - {speaker_air_ms:.2f})")
            print(f"        = {diff_corrected:.2f} ms")

    if psychopy_tubes and vpixx_tubes:
        mp = all_data[psychopy_tubes]['stats']['mean']
        mv = all_data[vpixx_tubes]['stats']['mean']
        sp = all_data[psychopy_tubes]['stats']['std']
        sv = all_data[vpixx_tubes]['stats']['std']
        diff = mp - mv
        sd_diff = np.sqrt(sp**2 + sv**2)
        print()
        print(f"PsychoPy backend overhead  (PsychoPy/tubes - VPIXX/tubes):")
        print(f"    = {mp:.2f} - {mv:.2f}")
        print(f"    = {diff:.2f} ms  (combined SD: {sd_diff:.2f} ms)")
        print(f"    Interpretation: the additional latency incurred by")
        print(f"    routing audio through the PsychoPy PTB software path")
        print(f"    versus VPIXX's hardware-scheduled audio path.")

    if not any([vpixx_tubes, psychopy_tubes, vpixx_speakers]):
        print("(No matching condition labels for derived comparisons.)")
    print("=" * 82)


# =============================================================================
# VISUALIZATION
# =============================================================================

def make_figure(all_data, out_path):
    """Build the analysis figure and save to `out_path`.

    Layout:
        Row 1: per-condition histograms (one subplot each) with
               vertical lines marking mean and median.
        Row 2: overlaid histograms of all conditions.
        Row 3: per-trial scatter for each condition (stability check).
    """
    labels = [lbl for lbl, d in all_data.items() if d['stats']['n'] > 0]
    n_conditions = len(labels)
    if n_conditions == 0:
        print("No data to plot.")
        return

    # Colors keyed to canonical roles when possible, else fall through
    color_by_role = {
        'vpixx-tubes':    '#1f77b4',   # blue
        'psychopy-tubes': '#d62728',   # red
        'vpixx-speakers': '#2ca02c',   # green
    }
    default_colors = ['#1f77b4', '#d62728', '#2ca02c', '#9467bd', '#ff7f0e']

    def color_for(label):
        l = label.lower()
        if 'vpixx' in l and 'tube' in l:
            return color_by_role['vpixx-tubes']
        if 'psychopy' in l and 'tube' in l:
            return color_by_role['psychopy-tubes']
        if 'vpixx' in l and 'speaker' in l:
            return color_by_role['vpixx-speakers']
        return default_colors[labels.index(label) % len(default_colors)]

    fig = plt.figure(figsize=(15, 11))
    gs  = GridSpec(3, max(n_conditions, 1), figure=fig,
                    hspace=0.42, wspace=0.32,
                    top=0.94, bottom=0.06, left=0.06, right=0.98)

    # --- Row 1: individual histograms ---
    for i, label in enumerate(labels):
        ax  = fig.add_subplot(gs[0, i])
        lat = all_data[label]['latencies_ms']
        s   = all_data[label]['stats']
        c   = color_for(label)

        ax.hist(lat, bins=30, color=c, alpha=0.75, edgecolor='white', linewidth=0.6)
        ax.axvline(s['mean'],   color='black', linewidth=1.5,
                    label=f"mean   = {s['mean']:.2f} ms")
        ax.axvline(s['median'], color='black', linewidth=1.5, linestyle='--',
                    label=f"median = {s['median']:.2f} ms")
        ax.set_xlabel('Latency (ms)')
        ax.set_ylabel('Trials')
        ax.set_title(f"{label}\n(N = {s['n']}, SD = {s['std']:.2f} ms)",
                      fontsize=10)
        ax.legend(fontsize=8, loc='upper right', frameon=True)
        ax.grid(alpha=0.3)

    # --- Row 2: overlaid histograms ---
    ax_overlay = fig.add_subplot(gs[1, :])
    for label in labels:
        lat = all_data[label]['latencies_ms']
        s   = all_data[label]['stats']
        c   = color_for(label)
        ax_overlay.hist(
            lat, bins=60, alpha=0.55, color=c, edgecolor=c, linewidth=0.6,
            label=f"{label}   mean={s['mean']:.2f}  SD={s['std']:.2f}  (N={s['n']})",
        )
    ax_overlay.set_xlabel('Latency (ms)')
    ax_overlay.set_ylabel('Trials')
    ax_overlay.set_title('Overlaid histograms (direct comparison)', fontsize=11)
    ax_overlay.legend(fontsize=9, loc='upper right', frameon=True)
    ax_overlay.grid(alpha=0.3)

    # --- Row 3: per-trial scatter (stability check) ---
    ax_scatter = fig.add_subplot(gs[2, :])
    for label in labels:
        lat = all_data[label]['latencies_ms']
        c   = color_for(label)
        trials = np.arange(1, len(lat) + 1)
        ax_scatter.scatter(trials, lat, s=10, alpha=0.7, color=c, label=label,
                            edgecolors='none')
    ax_scatter.set_xlabel('Trial number')
    ax_scatter.set_ylabel('Latency (ms)')
    ax_scatter.set_title('Per-trial latency (drift / stability check)', fontsize=11)
    ax_scatter.legend(fontsize=9, loc='upper right', frameon=True)
    ax_scatter.grid(alpha=0.3)

    fig.suptitle('BBTK Audio Latency Analysis', fontsize=13, fontweight='bold')

    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"\nFigure saved: {out_path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    # Parse each RTL file, compute latencies, gather stats
    all_data = {}
    for label, filepath in INPUT_FILES.items():
        if not Path(filepath).exists():
            print(f"WARNING: file not found, skipping: {filepath}")
            continue
        print(f"Parsing {filepath!r} ...")
        events, header = parse_rtl(filepath)
        latencies_ms, dropped = compute_latencies(events)
        stats = summarize(latencies_ms, label)
        all_data[label] = {
            'filepath':      filepath,
            'header':        header,
            'events':        events,
            'latencies_ms':  latencies_ms,
            'stats':         stats,
        }
        n_trigger_events = sum(1 for e in events if e['trigger_high'])
        print(f"    events: {len(events)}, "
              f"paired trials: {stats['n']}, "
              f"dropped (no mic edge in window): {dropped}")

    if not all_data:
        print("No RTL files found. Check INPUT_FILES at the top of the script.")
        return

    # Summary tables
    print_summary_table(all_data)
    print_derived_comparisons(all_data)

    # Figure
    os.makedirs(FIGURES_DIR, exist_ok=True)
    out_path = os.path.join(FIGURES_DIR, 'audio_latency_analysis.png')
    make_figure(all_data, out_path)


if __name__ == '__main__':
    main()
