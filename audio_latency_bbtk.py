#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Audio Latency Measurement via BBTK
========================================================================

PURPOSE
-------
Measure the acoustic transit delay of the OPM-MEG headphone system --
i.e. the time from the software/hardware trigger that starts audio
playback to the moment the sound emerges at the earpiece. This latency
is dominated by the pneumatic tubing but also includes DAC output
buffer, amplifier, and driver contributions.

The measured value is a constant offset that tightly time-locked auditory
analysis) should be corrected by.

SETUP
-----
    VPIXX DOUT (Pixel Mode B) --> BBTK digital input channel 1
    Microphone at earpiece    --> BBTK digital input channel 2
                                  (via preamp / threshold detector
                                  if the mic itself is analog; or
                                  direct-in if the mic module already
                                  emits TTL on sound detection)

Both channels feed the same BBTK. On each trial the script fires a
pixel-mode trigger at the exact vsync that starts audio playback via
the VPIXX audio schedule; a moment later the sound emerges at the
earpiece and the mic reports it to BBTK. Both events are timestamped
by BBTK on a single clock, so their difference is the audio-path
latency (tube + any BBTK detection delay), free of cross-device clock
reconciliation.

Configure the BBTK software (BBTKPy / BBTK Software Suite) for:
    - Channel 1 name: pixel_trigger  (rising edge, TTL)
    - Channel 2 name: mic            (rising edge on sound onset)
    - Sample rate  : as high as your BBTK model supports (1 kHz or
                     4 kHz typical)
    - Recording    : begin recording BEFORE starting this script;
                     stop after the script exits
    - Export       : one row per detected edge, with timestamps

For each trial the BBTK file should contain a pair of events:
    pixel_trigger @ t_N
    mic           @ t_N + latency

The distribution of (t_mic - t_pixel_trigger) over 200 trials is your
latency measurement. Mean = the correction constant to apply in
analysis. SD tells you jitter of the audio path.


STIMULUS OPTIONS
----------------
Three tone types are available, selectable via TONE_TYPE:

    'sine'  : 1000 Hz sine, 100 ms, 5 ms cosine on/off ramps.
              Matches the frequency of the paradigm's standard tone.
              Ramp softens the onset transient a little, which slightly
              delays the mic's threshold crossing but is a fair proxy
              for what the paradigm actually plays.

    'click' : 2 ms rectangular pulse with 0.5 ms cosine ramps at
              edges. Sharpest possible onset -> most accurate onset-
              time detection at the mic. Broadband spectrum. Best if
              you want ground-truth acoustic latency of the tubing
              itself (independent of the specific tone content).

    'noise' : 500 Hz-wide band noise burst centered on 1000 Hz,
              100 ms, 5 ms cosine on/off ramps. Excites the tube's
              acoustic response across a range near the paradigm's
              tone frequency. Useful for detecting frequency-dependent
              transit differences (usually negligible for short tubes,
              but worth a quick check).

Recommendation: measure with 'click' for the sharpest reference, then
also run 'sine' to confirm the latency you'll apply to your paradigm's
actual stimuli. Difference should be small (a few hundred us at most).

TIMING
------
Per trial:
    1. Configure the VPIXX audio schedule (once per tone).
    2. DPxStartAudSched (arm on local register).
    3. Set trigger pixel color to TRIGGER_ON.
    4. DPxWriteRegCacheAfterVideoSync (queue push at next vsync).
    5. win.flip() unblocks at the vsync -> audio and MEG trigger edge
       fire together.
    6. Wait for tone_duration.
    7. Set trigger pixel to TRIGGER_RESET, flip.
    8. Wait for jittered ISI (1.8-2.2 s).


BACKUP CSV
----------
A per-trial CSV log is written to disk alongside the BBTK file. Its
purpose is to sanity-check trial count, spot any obviously-anomalous
trials at load time, and provide a second view if the BBTK export is
ever ambiguous. Columns:
    trial       - 1..N_TRIALS
    hw_onset    - VPIXX hardware timestamp of the tone vsync (s)
    planned_isi - jittered ISI following this trial (s)
Not used for latency computation -- that comes from the BBTK file.

CONTROLS
--------
    SPACE : begin the measurement (from the "ready" screen)
    ESC   : abort mid-run (writes what's been logged so far)
"""

# =============================================================================
# IMPORTS
# =============================================================================

import os
import sys
import csv

import numpy as np
from psychopy import visual, core, event, gui, data, logging
from pypixxlib import _libdpx as dp

logging.console.setLevel(logging.CRITICAL)

# Switch to the script folder so relative paths work
script_path = os.path.dirname(sys.argv[0])
if len(script_path) != 0:
    os.chdir(script_path)


# =============================================================================
# EXPERIMENT PARAMETERS
# =============================================================================

# --- Stimulus type: pick one ---
# Read the STIMULUS OPTIONS section of the docstring before choosing.
TONE_TYPE = 'sine'         # 'sine' | 'click' | 'noise'

# --- Trial structure ---
N_TRIALS  = 200            # per BBTK measurement session
ISI_MIN   = 1.800          # seconds
ISI_MAX   = 2.200          # seconds

# --- Common audio params ---
AUDIO_SAMPLE_RATE = 48000  # Hz for VPIXX audio codec
AUDIO_AMPLITUDE   = 0.8    # 0-1, scales the peak of the int16 waveform

# --- 'sine' waveform ---
SINE_FREQ     = 1000       # Hz
SINE_DURATION = 0.100      # seconds
SINE_RAMP     = 0.005      # seconds cosine on/off

# --- 'click' waveform ---
# Rectangular pulse with very short cosine ramps on the edges. The
# 0.5 ms ramps avoid the offset click producing a spurious second
# BBTK event; the onset ramp is short enough not to noticeably delay
# the mic's threshold crossing.
CLICK_DURATION = 0.002     # seconds (2 ms)
CLICK_RAMP     = 0.0005    # seconds (0.5 ms) cosine on/off

# --- 'noise' waveform ---
NOISE_CENTER_FREQ = 1000   # Hz (centered on paradigm's tone freq)
NOISE_BANDWIDTH   = 500    # Hz total (250 Hz on each side of center)
NOISE_DURATION    = 0.100  # seconds
NOISE_RAMP        = 0.005  # seconds cosine on/off

# --- Trigger pixel (VPIXX Pixel Mode B) ---
TRIGGER_PATCH_SIZE = 1
TRIGGER_ON         = 1     # blue channel value at tone onset
TRIGGER_RESET      = 0     # blue channel value between tones

# --- VPIXX audio buffer address ---
AUDIO_BUFFER_ADDR = int(16.0e6)   # 16,000,000 (VPIXX default)


# =============================================================================
# WAVEFORM GENERATORS
# =============================================================================

def _apply_cosine_ramps(wave, n_ramp):
    """Apply cosine on/off ramps to a waveform in-place. Returns wave."""
    if n_ramp <= 0:
        return wave
    ramp_up   = 0.5 * (1.0 - np.cos(np.pi * np.arange(n_ramp) / n_ramp))
    ramp_down = 0.5 * (1.0 + np.cos(np.pi * np.arange(n_ramp) / n_ramp))
    wave[:n_ramp]  *= ramp_up
    wave[-n_ramp:] *= ramp_down
    return wave


def _to_int16(wave, amplitude):
    """Scale a float waveform in [-1, +1] to int16 for the VPIXX buffer."""
    wave = np.clip(wave * amplitude, -1.0, 1.0)
    return (wave * 32767.0).astype(np.int16)


def make_sine(frequency, duration, sample_rate, ramp_duration, amplitude):
    """Sine tone with cosine on/off ramps."""
    n_samples = int(duration * sample_rate)
    n_ramp    = int(ramp_duration * sample_rate)
    t = np.linspace(0, duration, n_samples, endpoint=False)
    wave = np.sin(2.0 * np.pi * frequency * t)
    wave = _apply_cosine_ramps(wave, n_ramp)
    return _to_int16(wave, amplitude)


def make_click(duration, sample_rate, ramp_duration, amplitude):
    """Rectangular pulse with short cosine ramps to suppress offset click.

    Onset ramp is intentionally short (~0.5 ms by default) so it does not
    noticeably delay the mic's threshold crossing at BBTK. The offset
    ramp prevents a spurious second edge at the tone's end.
    """
    n_samples = int(duration * sample_rate)
    n_ramp    = int(ramp_duration * sample_rate)
    wave = np.ones(n_samples, dtype=np.float64)
    wave = _apply_cosine_ramps(wave, n_ramp)
    return _to_int16(wave, amplitude)


def make_noise_burst(center_freq, bandwidth, duration, sample_rate,
                     ramp_duration, amplitude, seed=None):
    """Band-limited noise burst via FFT masking, with cosine on/off ramps.

    Uses numpy's FFT (no scipy dependency). The band is a rectangular
    window in the frequency domain from center - bw/2 to center + bw/2.
    Result is normalized so its peak matches `amplitude`.
    """
    n_samples = int(duration * sample_rate)
    n_ramp    = int(ramp_duration * sample_rate)

    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n_samples)

    # FFT bandpass
    fft   = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n_samples, d=1.0 / sample_rate)
    lo    = center_freq - bandwidth / 2.0
    hi    = center_freq + bandwidth / 2.0
    fft[(freqs < lo) | (freqs > hi)] = 0
    wave  = np.fft.irfft(fft, n=n_samples)

    # Normalize peak to 1 so ramps + amplitude behave predictably
    peak = np.max(np.abs(wave))
    if peak > 0:
        wave = wave / peak

    wave = _apply_cosine_ramps(wave, n_ramp)
    return _to_int16(wave, amplitude)


def build_stimulus(tone_type):
    """Dispatch to the requested waveform generator."""
    if tone_type == 'sine':
        wave = make_sine(SINE_FREQ, SINE_DURATION, AUDIO_SAMPLE_RATE,
                         SINE_RAMP, AUDIO_AMPLITUDE)
        label = f'sine {SINE_FREQ} Hz, {SINE_DURATION*1000:.0f} ms'
    elif tone_type == 'click':
        wave = make_click(CLICK_DURATION, AUDIO_SAMPLE_RATE,
                          CLICK_RAMP, AUDIO_AMPLITUDE)
        label = f'click {CLICK_DURATION*1000:.1f} ms'
    elif tone_type == 'noise':
        wave = make_noise_burst(NOISE_CENTER_FREQ, NOISE_BANDWIDTH,
                                NOISE_DURATION, AUDIO_SAMPLE_RATE,
                                NOISE_RAMP, AUDIO_AMPLITUDE)
        label = (f'noise burst {NOISE_CENTER_FREQ} Hz ± {NOISE_BANDWIDTH/2:.0f}, '
                 f'{NOISE_DURATION*1000:.0f} ms')
    else:
        raise ValueError(
            f"Unknown TONE_TYPE='{tone_type}'. "
            "Choose one of: 'sine', 'click', 'noise'."
        )
    return wave, label


# =============================================================================
# VPIXX HELPERS
# =============================================================================

def init_vpixx():
    """Open the VPIXX device, enable Pixel Mode B, and init audio codec."""
    dp.DPxOpen()
    dp.DPxStopAllScheds()
    dp.DPxEnableDoutPixelModeB()   # blue-channel-only trigger output
    dp.DPxInitAudCodec()           # initialize audio subsystem
    dp.DPxWriteRegCache()


def load_tone_into_buffer(tone_int16, buffer_addr):
    """Push the int16 waveform into DATAPixx3 RAM."""
    dp.DPxWriteAudioBuffer(tone_int16, buffer_addr)
    dp.DPxWriteRegCache()


def prep_tone_schedule(n_samples, buffer_addr):
    """Configure the audio schedule and push config to device.

    Does NOT arm the start bit. Caller must, immediately before
    win.flip(), call:
        dp.DPxStartAudSched()                # arm start bit (local reg)
        dp.DPxWriteRegCacheAfterVideoSync()  # queue push at next vsync
    """
    dp.DPxSetAudioSchedule(0.0, AUDIO_SAMPLE_RATE, n_samples,
                            'mono', buffer_addr)
    dp.DPxWriteRegCache()      # config now on device


def close_vpixx():
    """Cleanly disable pixel mode and disconnect."""
    try:
        dp.DPxDisableDoutPixelMode()
    except Exception:
        pass
    try:
        dp.DPxWriteRegCache()
    except Exception:
        pass
    try:
        dp.DPxClose()
    except Exception:
        pass


# =============================================================================
# COLOR HELPER
# =============================================================================

def rgb_255_to_psychopy(rgb):
    """Convert [R,G,B] in 0-255 to PsychoPy's default [-1,+1] color space."""
    return [(c / 127.5) - 1.0 for c in rgb]


def trigger_color(value):
    """Fill color for the trigger patch. Blue channel = trigger value."""
    return rgb_255_to_psychopy([0, 0, value])


# =============================================================================
# TERMINATE
# =============================================================================

def terminate(win, csv_path, trial_log):
    """Write CSV, close VPIXX, close window, exit."""
    try:
        with open(csv_path, 'w', newline='') as f:
            w = csv.DictWriter(f,
                fieldnames=['trial', 'hw_onset', 'planned_isi'])
            w.writeheader()
            w.writerows(trial_log)
        print(f"CSV saved: {csv_path}")
    except Exception as e:
        print(f"WARNING writing CSV: {e}")

    close_vpixx()

    if win is not None:
        try:
            win.close()
        except Exception:
            pass

    core.quit()
    sys.exit()


# =============================================================================
# MAIN
# =============================================================================

# --- Session info dialog ---
info = {'measurement_id': '', 'tone_type': TONE_TYPE}
dlg = gui.DlgFromDict(dictionary=info,
                      title='Audio Latency Measurement',
                      order=['measurement_id', 'tone_type'])
if not dlg.OK:
    core.quit()

TONE_TYPE = info['tone_type']    # allow override from dialog
info['date'] = data.getDateStr()

# --- Output CSV path ---
results_folder = 'results_latency'
os.makedirs(results_folder, exist_ok=True)

mid = info['measurement_id'].strip() or 'unnamed'
mid = mid.replace('/', '_').replace(' ', '_')
csv_path = os.path.join(
    results_folder,
    f'audio_latency_{mid}_{TONE_TYPE}_{info["date"]}.csv'
)


# --- VPIXX init ---
init_vpixx()


# --- Build and load stimulus ---
stim_wave, stim_label = build_stimulus(TONE_TYPE)
stim_n_samples = int(len(stim_wave))
load_tone_into_buffer(stim_wave, AUDIO_BUFFER_ADDR)

print(f"Stimulus: {stim_label}")
print(f"Duration: {stim_n_samples / AUDIO_SAMPLE_RATE * 1000:.2f} ms "
      f"({stim_n_samples} samples @ {AUDIO_SAMPLE_RATE} Hz)")


# --- Precompute jittered ISIs ---
rng  = np.random.default_rng()
isis = rng.uniform(ISI_MIN, ISI_MAX, size=N_TRIALS)

est_min = N_TRIALS * ((ISI_MIN + ISI_MAX) / 2.0) / 60.0
print(f"Estimated total time: ~{est_min:.1f} min "
      f"({N_TRIALS} trials, ISI {ISI_MIN}-{ISI_MAX} s)")


# --- Window (fullscreen on the VPIXX display) ---
win = visual.Window(
    fullscr=True,
    color=[0, 0, 0],
    colorSpace='rgb255',
    units='pix',
    allowGUI=False,
    screen=0,
)
win_w, win_h = win.size


# --- Trigger patch: 1x1 in upper-left corner ---
trigger_x = -win_w / 2.0 + TRIGGER_PATCH_SIZE / 2.0
trigger_y =  win_h / 2.0 - TRIGGER_PATCH_SIZE / 2.0
trigger_patch = visual.Rect(
    win,
    width=TRIGGER_PATCH_SIZE, height=TRIGGER_PATCH_SIZE,
    pos=(trigger_x, trigger_y),
    lineWidth=0,
    fillColor=trigger_color(TRIGGER_RESET),
    fillColorSpace='rgb',
)


# --- Screen text: instructions, progress ---
instr = visual.TextStim(
    win,
    text=(
        "Audio Latency Measurement\n\n"
        f"Stimulus       : {stim_label}\n"
        f"Trials         : {N_TRIALS}\n"
        f"ISI            : {ISI_MIN}-{ISI_MAX} s (jittered)\n\n"
        "Confirm the BBTK is:\n"
        "  - Recording\n"
        "  - Channel 1 wired to VPIXX DOUT (pixel_trigger)\n"
        "  - Channel 2 wired to earpiece mic (mic)\n\n"
        "Press SPACE to begin measurement.\n"
        "Press ESC to abort at any time."
    ),
    color='white', height=26, wrapWidth=1000,
)
progress = visual.TextStim(
    win, text='', color='white', height=24, pos=(0, 0),
)


# --- Ready screen: wait for experimenter ---
instr.draw()
trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
trigger_patch.draw()
win.flip()
keys = event.waitKeys(keyList=['space', 'escape'])
if 'escape' in keys:
    terminate(win, csv_path, [])


# --- Brief pause with blank + reset trigger so BBTK sees a clean baseline ---
trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
trigger_patch.draw()
win.flip()
core.wait(2.0)


# --- Measurement loop ---
trial_log = []

for trial_num in range(N_TRIALS):

    # Progress readout for the experimenter (drawn every trial; small
    # text so it doesn't dominate the black screen)
    progress.text = f"Trial {trial_num + 1} / {N_TRIALS}"

    # 1. Configure the audio schedule and push config to device
    prep_tone_schedule(stim_n_samples, AUDIO_BUFFER_ADDR)

    # 2. Prep visual: trigger patch on + progress text
    progress.draw()
    trigger_patch.fillColor = trigger_color(TRIGGER_ON)
    trigger_patch.draw()

    # 3. Arm audio + queue register push at next vsync
    dp.DPxStartAudSched()
    dp.DPxWriteRegCacheAfterVideoSync()

    # 4. Flip: MEG trigger edge on DOUT and audio playback both fire
    #    at this vsync
    win.flip()
    hw_onset = dp.DPxGetTime()

    # 5. Wait for tone duration (visual trigger stays high across it)
    tone_dur = stim_n_samples / AUDIO_SAMPLE_RATE
    core.wait(tone_dur)

    # 6. Reset trigger to 0 during ISI
    progress.draw()
    trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
    trigger_patch.draw()
    win.flip()

    # 7. Log for CSV
    isi = float(isis[trial_num])
    trial_log.append({
        'trial':       trial_num + 1,
        'hw_onset':    f"{hw_onset:.6f}",
        'planned_isi': f"{isi:.4f}",
    })

    # 8. Wait ISI (checking for abort periodically)
    # Use a slightly interruptible wait so ESC is responsive.
    elapsed = 0.0
    step    = 0.100
    while elapsed < isi:
        remaining = min(step, isi - elapsed)
        core.wait(remaining)
        elapsed += remaining
        if event.getKeys(keyList=['escape']):
            print(f"\nAborted at trial {trial_num + 1}.")
            terminate(win, csv_path, trial_log)


# --- Done ---
done = visual.TextStim(
    win,
    text=(
        "Measurement complete.\n\n"
        f"{N_TRIALS} trials logged.\n"
        f"CSV: {os.path.basename(csv_path)}\n\n"
        "Stop the BBTK recording now.\n\n"
        "Press SPACE to exit."
    ),
    color='white', height=28, wrapWidth=1000,
)
done.draw()
trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
trigger_patch.draw()
win.flip()
event.waitKeys(keyList=['space', 'escape'])

print(f"\nCompleted {N_TRIALS} trials.")
print(f"Stimulus: {stim_label}")
print(f"CSV path: {csv_path}")
print("Now analyze the BBTK file to compute latency = "
      "t_mic - t_pixel_trigger for each pair of events.")

terminate(win, csv_path, trial_log)
