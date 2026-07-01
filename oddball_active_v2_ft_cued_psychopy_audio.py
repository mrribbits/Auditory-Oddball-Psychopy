#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Active Auditory Oddball, FieldTrip Cued Paradigm - v2 (PsychoPy audio)
========================================================================

OVERVIEW
--------
Bimanual cued active oddball for OPM-MEG. Replicates the FieldTrip
tutorial paradigm (Oostenveld et al.) as documented in their oddball
workshop figure. Each trial cues the subject to prepare a left- or
right-hand response, presents 3-7 standard tones followed by 1 deviant
tone, and requires a button press with the cued index finger. This
supports classical MMN/P3 analysis on tone-locked ERFs AND lateralized
post-movement beta rebound (PMBR) analysis on the cued hand contrast.

This is the PsychoPy-audio variant of the paradigm. It is IDENTICAL to
oddball_active_v2_ft_cued.py in every other respect (visuals, trigger
scheme, button decoding, EyeLink, block structure, CSV outputs). The
only difference is that tones are played through PsychoPy's built-in
audio backend instead of the VPIXX DATAPixx3 audio subsystem. Use this
version when you want to sanity-check the paradigm without VPIXX audio
hardware in the loop, or when comparing timing precision between the
two audio paths.

Structure (one trial = one cycle of the figure):

    +-----------+-----+-----------------+---------+----------+-------+
    | fixation  | cue | auditory stim   | resp.   | feedback | BLINK |
    |  1500 ms  |500ms|  4000-8800 ms   | 1000 ms |  400 ms  | 500 ms|
    |     +     | >+> | tones + oddball |    +    |  (errors |       |
    |           | or  |                 |         |   only)  |       |
    |           | <+< |                 |         |          |       |
    +-----------+-----+-----------------+---------+----------+-------+

Three blocks x 100 trials = 300 trials total, ~51 minutes recording
plus a ~3-minute training block at the start.


AUDIO STIMULI VIA PSYCHOPY AUDIO BACKEND
----------------------------------------
Both tones are generated as float32 arrays at experiment start and
wrapped in psychopy.sound.Sound objects. The audio backend is selected
via the prefs.hardware['audioLib'] preference (set at the top of this
script to ['ptb', 'sounddevice']): PTB is used if available, sounddevice
is the fallback for machines without psychtoolbox installed.

Per-tone sequence:

    1. Draw the visual frame (fixation + trigger pixel).

    2. Preschedule audio playback to hit the next vsync:
         when_ptb = win.getFutureFlipTime(clock='ptb')
         tone_stim.play(when=when_ptb)
       On the PTB backend this tells the audio engine "start playback
       at exactly this PTB-clock time" and it plans buffer submission
       accordingly. Sub-ms precision is achievable on typical hardware.
       On the sounddevice backend the script falls back to
       win.callOnFlip(tone_stim.play), which starts audio at the next
       audio-callback boundary after the flip -- typically 1-5 ms of
       lag with sub-ms jitter.

    3. win.flip()
       Blocks until the next vsync. At that vsync:
         - VPIXX reads the trigger pixel color from the framebuffer
           and puts it on DOUT -> MEG trigger channel edge rises
         - The prescheduled audio starts (on PTB, hardware-precisely)

    4. DPxGetTime -> capture the hardware timestamp of the vsync.

    5. After the tone has played, query the audio track's status to
       get the reported actual start time:
         requested, actual = get_audio_status(tone_stim)
       On PTB, these are populated with RequestedStartTime and
       StartTime from psychtoolbox's audio.Slave.status. Both are in
       the PTB clock (not the PsychoPy default clock). Their
       difference tells you the software delay between requested and
       actual audio onset. Logged as pp_audio_requested and
       pp_audio_actual in the tones CSV.

For definitive audio-to-MEG timing verification, compare the tones
CSV's pp_audio_actual column against your MEG trigger channel (from
the VPIXX DOUT pixel-mode trigger) and, ideally, a microphone signal
at the earpiece. The difference between MEG trigger edge and mic
signal is your combined software + tube latency, useful for MMN peak-
latency correction.

If you require deterministic sub-ms audio-to-trigger alignment
guaranteed at the hardware level (not just backend-precision), use the
VPIXX-audio variant (oddball_active_v2_ft_cued.py) instead. That
variant locks audio playback to the same vsync as the MEG trigger
edge via DPxWriteRegCacheAfterVideoSync.

The physical tube-to-ear transit through the OPM headphone system is a
separate constant acoustic latency that must be measured once with a
microphone at the earpiece (FieldTrip reports 7.0 ms for their sound
showers) and subtracted from MMN peak latencies in analysis. That
measurement is orthogonal to the audio-backend choice above.


TRIGGER SCHEME (VPIXX Pixel Mode B, blue channel only)
------------------------------------------------------
Sent by drawing a 1x1 patch in the upper-left corner:

    standard tone onset:   1
    deviant tone onset:    2
    blink cue onset:       4
    left cue onset:        8
    right cue onset:      16
    error feedback onset: 32
    (reset between events: 0)

Response events are NOT pixel-triggered. The ResponsePixx button
outputs feed directly into the OPM-MEG amplifier's trigger channels
(Mark's lab wiring), so button-press onsets are already recorded in
the MEG data stream with no software intervention needed.


TRIGGER vs. PERCEIVED-STIMULUS TIMING
-------------------------------------
All pixel-mode triggers fire at the vsync when win.flip() unblocks.
That vsync marks when the display BEGINS drawing the new frame from
the top; the pixels the subject actually sees are illuminated one
frame later (~8.33 ms at 120 Hz; ~16.7 ms at 60 Hz). The trigger
therefore LEADS the perceived visual stimulus by one frame.

For the AUDIO channel there is a small software latency between the
trigger vsync and the actual audio onset (PsychoPy backend copies
samples into the sound device's output buffer and waits for the next
audio callback boundary). Measure this offset once on your setup with
a microphone at the earpiece; it typically sits at 1-5 ms with sub-ms
jitter on modern PsychoPy backends. On top of that, the tone reaches
the ear a few ms later via the acoustic tubing (also measure once).
Total trigger-to-perceived-tone = software_audio_latency + tube_delay.

For VISUAL cues (cue arrow, error feedback, BLINK text) the trigger
leads perceived onset by one frame. When locking MEG/OPM analyses to
the moment the subject actually saw the stimulus (e.g. cue-locked
motor preparation, feedback-locked ERPs), subtract DISPLAY_FRAME_MS
from the trigger-channel edge time.

    Event                   MEG trigger edge -> subject perceives
    -----------------------  --------------------------------------
    Standard / deviant tone  + software_audio_latency + tube_delay
    Cue arrow                + one video frame (DISPLAY_FRAME_MS)
    BLINK text               + one video frame
    Error feedback           + one video frame

Button presses do NOT need any correction: the ResponsePixx feeds
directly into the MEG amplifier's trigger channels, so the response
edge in the MEG data IS the physical response time.


BUTTON DECODING
---------------
The ResponsePixx reports DIN state as a 16-bit integer with bits
10-15 always high (reserved), so the base "nothing pressed" state is
64512 (0b1111110000000000). Each button adds one bit in the low 10:

    64513  left_index      (bit 0)   64544  right_index    (bit 5)
    64514  left_middle     (bit 1)   64576  right_middle   (bit 6)
    64516  left_ring       (bit 2)   64640  right_ring     (bit 7)
    64520  left_pinky      (bit 3)   64768  right_pinky    (bit 8)
    64528  left_thumb      (bit 4)   65024  right_thumb    (bit 9)

Valid responses for this task: left_index (cue = left) or right_index
(cue = right). Any other single-button code is scored as wrong_button.
Chord events (multiple buttons at once) and unknown codes are logged
but not counted as responses.


RESPONSE SCORING
----------------
Valid response window: 150-1400 ms after deviant onset (150 ms floor
rejects anticipation; 1400 ms ceiling = deviant duration + response
phase, matching the figure).

Outcomes:
    correct       : cued hand's index finger, pressed in window
    wrong_button  : any other single-button press in window
    miss          : no valid press in window

Feedback (400 ms red text) is shown only for wrong_button and miss.
Correct trials go straight from the response window to the BLINK cue.


BLOCK STRUCTURE
---------------
    1. Training block (~3 min, 20 trials) at the start.
       Data logged separately, not counted in main summary.
    2. Main block 1 (~17 min, 100 trials).
    3. Between-block break: accuracy summary, drift check when
       experimenter presses SPACE.
    4. Main block 2 (~17 min).
    5. Between-block break + drift check.
    6. Main block 3 (~17 min).
    7. End screen with overall summary.

CSV logs are flushed at the end of every block (crash-safe: if the
experiment dies during block 2, block 1 data is on disk).
DIN log runs continuously across the whole session; between-block
breaks do not stop or restart it.


OUTPUT FILES
------------
results/sub-<p>_ses-<s>_task-oddballftcued/

    ..._trials.csv    one row per trial (main behavioral log)
    ..._tones.csv     one row per tone (per-tone hw timestamps)
    ..._presses.csv   one row per detected button-box event
    ....EDF           EyeLink data (from Host PC at experiment end)


PRE-FLIGHT CHECKLIST
--------------------
    1. VPIXX device is on and reachable (DPxOpen succeeds).
    2. VPIXX is running Pixel Mode B (this script enables it, but
       verify PyPixx doesn't override).
    3. PsychoPy audio backend is producing sound on the OPM lab's
       output path (test tone before running).
    4. ResponsePixx is connected; run vpixx_button_test.py once to
       confirm the button codes above match what your box reports.
    5. EyeLink Host PC at 100.1.1.1, or set DUMMY_MODE=True.
    6. Audio timing has been measured for your OPM lab (trigger-to-
       ear delay via microphone at earpiece; record in experiment
       metadata for MMN latency correction).
"""

# =============================================================================
# IMPORTS
# =============================================================================

import os
import sys
import csv
import json

import numpy as np

# Set the audio backend preference BEFORE importing psychopy.sound.
# PTB (psychtoolbox) is preferred: it supports precise pre-scheduling
# (sub-ms audio precision) and exposes reported actual start times via
# psychtoolbox's audio.Slave.status. sounddevice is a legitimate
# fallback that ships with PsychoPy 2026.1+ and does not require
# psychtoolbox to be installed, but audio timing is less precise and
# reported-start-time info may be unavailable.
from psychopy import prefs
prefs.hardware['audioLib'] = ['ptb', 'sounddevice']

from psychopy import visual, sound, core, event, gui, data, logging
import pylink
from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy
from pypixxlib import _libdpx as dp

logging.console.setLevel(logging.CRITICAL)

# Switch to the script folder so relative paths work
script_path = os.path.dirname(sys.argv[0])
if len(script_path) != 0:
    os.chdir(script_path)


# =============================================================================
# EXPERIMENT PARAMETERS
# =============================================================================

# --- Tones ---
STANDARD_FREQ     = 1000        # Hz
DEVIANT_FREQ      = 1200        # Hz
TONE_DURATION     = 0.400       # seconds
RAMP_DURATION     = 0.050       # seconds cosine on/off
AUDIO_SAMPLE_RATE = 48000       # Hz for VPIXX audio codec
AUDIO_AMPLITUDE   = 0.8         # 0-1 (mapped to int16)

# --- Trial structure ---
N_BLOCKS              = 3       # main experiment blocks
N_TRIALS_PER_BLOCK    = 100     # trials per block
N_TRAINING_TRIALS     = 20      # short training block (skippable via flag)
RUN_TRAINING          = True    # False skips training entirely
MIN_STANDARDS         = 3       # min standards before each oddball
MAX_STANDARDS         = 7       # max standards before each oddball

# --- Timing (all seconds; matches FT figure exactly) ---
FIXATION_DURATION = 1.500       # baseline fixation before cue
CUE_DURATION      = 0.500       # cue arrow visible time
ISI_MIN           = 0.700       # inter-tone offset->onset min
ISI_MAX           = 0.900       # inter-tone offset->onset max
RESPONSE_WINDOW   = 1.000       # fixation-only response phase after deviant
FEEDBACK_DURATION = 0.400       # only shown on errors
BLINK_DURATION    = 0.500       # BLINK text after every trial

# --- Response scoring (relative to deviant onset) ---
RESP_WIN_MIN = 0.150            # reject anticipatory presses
RESP_WIN_MAX = TONE_DURATION + RESPONSE_WINDOW   # 1.400 s

# --- Blocks / breaks ---
INTERBLOCK_MIN_REST = 15.0      # seconds before SPACE is accepted at break
                                # (set to 0.0 for no minimum)

# --- Trigger pixel (VPIXX Pixel Mode B) ---
# Values are the blue channel of a 1x1 upper-left patch. The red and
# green channels are always 0. Values chosen as distinct powers of 2
# so combined triggers (unlikely here) would be OR-decodable.
TRIGGER_PATCH_SIZE = 1
TRIGGER_STANDARD   = 1          # standard tone onset
TRIGGER_DEVIANT    = 2          # deviant tone onset
TRIGGER_BLINK      = 4          # BLINK cue onset
TRIGGER_CUE_LEFT   = 8          # left cue onset
TRIGGER_CUE_RIGHT  = 16         # right cue onset
TRIGGER_FEEDBACK   = 32         # error feedback onset (either kind)
TRIGGER_RESET      = 0          # off, between events

# --- Display timing correction (informational; NOT used at runtime) ---
# Pixel-mode triggers fire at vsync, which is when the display BEGINS
# drawing a frame. Pixels the subject actually sees are illuminated one
# frame later. For MEG analyses locked to perceived visual-stimulus
# onset (cue arrow, feedback text, BLINK text), subtract this constant
# from the trigger-channel edge time. Audio events do NOT need this
# correction (audio starts at vsync too; the trigger-channel edge marks
# when audio playback begins).
DISPLAY_FRAME_MS = 8.33         # 120 Hz refresh; use 16.67 for 60 Hz

# --- Button box (ResponsePixx via VPIXX DIN) ---
BUTTON_RELEASE = 64512
BUTTON_CODES = {
    64513: 'left_index',
    64514: 'left_middle',
    64516: 'left_ring',
    64520: 'left_pinky',
    64528: 'left_thumb',
    64544: 'right_index',
    64576: 'right_middle',
    64640: 'right_ring',
    64768: 'right_pinky',
    65024: 'right_thumb',
}
# Which button is the correct response for each cue direction:
EXPECTED_BUTTONS = {'left': 'left_index', 'right': 'right_index'}

# --- EyeLink ---
DUMMY_MODE = False   # True skips EyeLink (development-only)
EYELINK_IP = "100.1.1.1"
CAL_TYPE   = "HV13"  # 13-point calibration


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_tone(frequency, duration, sample_rate,
              ramp_duration, amplitude=AUDIO_AMPLITUDE):
    """Generate a pure sine tone with cosine on/off ramps as float32.

    Returns a 1-D numpy array of float32 samples in the range
    [-amplitude, +amplitude], suitable for wrapping in a
    psychopy.sound.Sound object.
    """
    n_samples = int(duration * sample_rate)
    n_ramp    = int(ramp_duration * sample_rate)

    t = np.linspace(0, duration, n_samples, endpoint=False)
    tone = np.sin(2.0 * np.pi * frequency * t)

    # Cosine on/off ramps to avoid click artefacts at onset/offset.
    ramp_up   = 0.5 * (1.0 - np.cos(np.pi * np.arange(n_ramp) / n_ramp))
    ramp_down = 0.5 * (1.0 + np.cos(np.pi * np.arange(n_ramp) / n_ramp))
    tone[:n_ramp]  *= ramp_up
    tone[-n_ramp:] *= ramp_down

    tone = (tone * amplitude).astype(np.float32)
    return tone


def rgb_255_to_psychopy(rgb):
    """Convert an [R,G,B] triple in 0-255 to PsychoPy's default [-1,+1] space."""
    return [(c / 127.5) - 1.0 for c in rgb]


def trigger_color(value):
    """Return the PsychoPy fill color that sets Pixel Mode B trigger to `value`.

    Blue channel = trigger value; red and green channels = 0.
    """
    return rgb_255_to_psychopy([0, 0, value])


def get_audio_status(tone_stim):
    """Query the audio backend for requested and actual playback start times.

    On the PTB backend, psychtoolbox's audio.Slave exposes a `status`
    dict containing:
        RequestedStartTime : the time we asked playback to begin
        StartTime          : the real time playback actually began
    Both are in the PTB clock (separate from PsychoPy's default clock).

    Returns
    -------
    requested : float or None
        Reported requested start time (PTB clock), or None if the
        backend does not expose it, or if playback has not yet begun.
    actual : float or None
        Reported actual start time (PTB clock), or None.

    Silent no-op on backends that do not expose track status
    (e.g. sounddevice in some configurations). Both return values will
    be None on those backends -- in which case the corresponding CSV
    columns will be empty and you should rely on a microphone-at-
    earpiece measurement for audio-to-MEG-trigger latency.
    """
    try:
        track = getattr(tone_stim, 'track', None)
        if track is None:
            return None, None

        status = getattr(track, 'status', None)
        # In some psychtoolbox-python versions .status is a property
        # returning a dict; in others it's a method that must be called.
        if callable(status):
            try:
                status = status()
            except Exception:
                return None, None

        if not isinstance(status, dict):
            return None, None

        # PTB uses MATLAB-style capitalized keys. Support the camelCase
        # variant just in case a future release changes the convention.
        requested = status.get('RequestedStartTime',
                               status.get('requestedStartTime'))
        actual    = status.get('StartTime',
                               status.get('startTime'))

        # Zero values are sometimes used as "not yet populated" sentinel.
        if requested == 0.0:
            requested = None
        if actual == 0.0:
            actual = None
        return requested, actual
    except Exception:
        return None, None


def decode_din_event(din_state):
    """Classify one DIN event into ('press'|'release'|'unknown', label).

    Returns
    -------
    kind : str
        'press'    -> clean single-button press (label = button name)
        'release'  -> all buttons up (label = None)
        'unknown'  -> chord or unrecognized code (label = raw din_state as str)
    """
    if din_state == BUTTON_RELEASE:
        return ('release', None)
    label = BUTTON_CODES.get(din_state)
    if label is not None:
        return ('press', label)
    return ('unknown', str(din_state))


def generate_block_sequence(n_trials, min_std, max_std,
                            isi_min, isi_max, seed=None):
    """Build the trial list for one block.

    Cues are balanced 50/50 left/right within the block and shuffled.
    Each trial's `n_standards` is drawn uniformly from [min_std, max_std].
    ISIs between consecutive tones are drawn uniformly from [isi_min, isi_max].

    Returns
    -------
    trials : list of dict
        Each dict has keys 'cue_hand', 'n_standards', 'isis'.
        'isis' has length n_standards (one ISI per gap between the
        n_standards + 1 tones).
    """
    rng = np.random.default_rng(seed)

    # Balanced 50/50 cues
    half = n_trials // 2
    cues = ['left'] * half + ['right'] * half
    if n_trials % 2 == 1:
        cues.append(rng.choice(['left', 'right']))
    rng.shuffle(cues)

    trials = []
    for cue in cues:
        n_std = int(rng.integers(min_std, max_std + 1))
        isis  = rng.uniform(isi_min, isi_max, size=n_std).tolist()
        trials.append({
            'cue_hand':    cue,
            'n_standards': n_std,
            'isis':        isis,
        })
    return trials


# =============================================================================
# VPIXX HELPERS
# =============================================================================

def init_vpixx():
    """Open the VPIXX device and enable Pixel Mode B.

    Audio is handled by PsychoPy in this variant, so DPxInitAudCodec
    is NOT called. Pixel-mode triggers and DIN button logging still
    run through VPIXX as normal.
    """
    dp.DPxOpen()
    dp.DPxStopAllScheds()
    dp.DPxEnableDoutPixelModeB()   # blue-channel-only trigger output
    dp.DPxWriteRegCache()


def drain_din_log(my_log):
    """Read all new DIN events and return them as a list of dicts.

    Each dict has: kind ('press'|'release'|'unknown'), label, hw_time.
    """
    dp.DPxUpdateRegCache()
    dp.DPxGetDinStatus(my_log)
    n_new = my_log['newLogFrames']
    if n_new <= 0:
        return []

    raw_events = dp.DPxReadDinLog(my_log, n_new)
    events = []
    for raw in raw_events:
        hw_time   = raw[0]
        din_state = raw[1]
        kind, label = decode_din_event(din_state)
        events.append({
            'kind':    kind,
            'label':   label,
            'hw_time': hw_time,
        })
    return events


def close_vpixx():
    """Cleanly disable pixel mode, stop DIN log, and disconnect."""
    try:
        dp.DPxDisableDoutPixelMode()
    except Exception:
        pass
    try:
        dp.DPxStopDinLog()
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
# EYELINK HELPERS
# =============================================================================

def connect_eyelink(dummy_mode, edf_fname):
    """Connect to the EyeLink Host PC and open a data file."""
    if dummy_mode:
        el_tracker = pylink.EyeLink(None)
    else:
        try:
            el_tracker = pylink.EyeLink(EYELINK_IP)
        except RuntimeError as err:
            print(f"ERROR connecting to EyeLink: {err}")
            core.quit()
            sys.exit()

    try:
        el_tracker.openDataFile(edf_fname)
    except RuntimeError as err:
        print(f"ERROR opening EDF: {err}")
        if el_tracker.isConnected():
            el_tracker.close()
        core.quit()
        sys.exit()

    preamble = f"RECORDED BY {os.path.basename(__file__)}"
    el_tracker.sendCommand(f"add_file_preamble_text '{preamble}'")
    el_tracker.setOfflineMode()
    return el_tracker


def configure_eyelink(el_tracker, scn_width, scn_height, dummy_mode):
    """Set event/sample filters and screen coordinates."""
    eyelink_ver = 0
    if not dummy_mode:
        vstr = el_tracker.getTrackerVersionString()
        eyelink_ver = int(vstr.split()[-1].split('.')[0])
        print(f"EyeLink: {vstr}")

    file_event = ('LEFT,RIGHT,FIXATION,SACCADE,BLINK,'
                  'MESSAGE,BUTTON,INPUT')
    link_event = ('LEFT,RIGHT,FIXATION,SACCADE,BLINK,'
                  'BUTTON,FIXUPDATE,INPUT')
    if eyelink_ver > 3:
        file_sample = ('LEFT,RIGHT,GAZE,HREF,RAW,AREA,HTARGET,'
                       'GAZERES,BUTTON,STATUS,INPUT')
        link_sample = ('LEFT,RIGHT,GAZE,GAZERES,AREA,HTARGET,'
                       'STATUS,INPUT')
    else:
        file_sample = ('LEFT,RIGHT,GAZE,HREF,RAW,AREA,'
                       'GAZERES,BUTTON,STATUS,INPUT')
        link_sample = ('LEFT,RIGHT,GAZE,GAZERES,AREA,'
                       'STATUS,INPUT')

    el_tracker.sendCommand(f"file_event_filter = {file_event}")
    el_tracker.sendCommand(f"file_sample_data = {file_sample}")
    el_tracker.sendCommand(f"link_event_filter = {link_event}")
    el_tracker.sendCommand(f"link_sample_data = {link_sample}")
    el_tracker.sendCommand(f"calibration_type = {CAL_TYPE}")

    el_tracker.sendCommand(
        f"screen_pixel_coords = 0 0 {scn_width - 1} {scn_height - 1}"
    )
    el_tracker.sendMessage(
        f"DISPLAY_COORDS 0 0 {scn_width - 1} {scn_height - 1}"
    )


def do_drift_check_between_blocks(el_tracker, scn_width, scn_height,
                                   dummy_mode):
    """Stop recording, run a drift correct, restart recording.

    Called during between-block breaks. Keeping recording off for the
    drift check is the safest pattern (avoids weird behavior in the
    EDF if the check is aborted).
    """
    if dummy_mode:
        return
    el_tracker.stopRecording()
    el_tracker.setOfflineMode()
    try:
        el_tracker.doDriftCorrect(int(scn_width / 2), int(scn_height / 2),
                                   1, 1)
    except Exception:
        pass
    el_tracker.startRecording(1, 1, 1, 1)
    pylink.pumpDelay(100)


# =============================================================================
# CSV FLUSH HELPERS
# =============================================================================

def write_trials_csv(filename, rows):
    """Write the trial-level CSV (cumulative, overwritten each flush)."""
    fields = ['overall_trial', 'block', 'trial_in_block', 'is_training',
              'cue_hand', 'expected_button', 'n_standards',
              'fixation_onset', 'cue_onset', 'cue_hw_onset',
              'first_tone_hw_onset', 'deviant_hw_onset',
              'response_button', 'response_hw_time', 'rt',
              'outcome', 'feedback_shown', 'blink_onset']
    with open(filename, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def write_tones_csv(filename, rows):
    """Write the per-tone CSV (cumulative, overwritten each flush).

    Columns:
        overall_trial, block, trial_in_block, tone_index, kind,
        frequency         - Hz
        psychopy_onset    - default PsychoPy clock, from win.flip()
        hw_onset          - VPIXX hardware clock, from DPxGetTime()
        pp_audio_requested- PTB clock, backend RequestedStartTime
                            (empty on non-PTB backends)
        pp_audio_actual   - PTB clock, backend reported StartTime
                            (empty on non-PTB backends)
        isi_after         - seconds until the next tone
    """
    fields = ['overall_trial', 'block', 'trial_in_block', 'tone_index',
              'kind', 'frequency', 'psychopy_onset', 'hw_onset',
              'pp_audio_requested', 'pp_audio_actual',
              'isi_after']
    with open(filename, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def write_presses_csv(filename, rows):
    """Write the raw button-event CSV (cumulative, overwritten each flush)."""
    fields = ['context', 'overall_trial', 'block', 'kind', 'label',
              'hw_time']
    with open(filename, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


# =============================================================================
# TERMINATE
# =============================================================================

def terminate_task(win, el_tracker, edf_file, session_folder,
                    local_edf_name, dummy_mode=False):
    """Stop EL recording, download EDF, close VPIXX, close window."""
    if el_tracker is not None and el_tracker.isConnected():
        if el_tracker.isRecording() == pylink.TRIAL_OK:
            pylink.pumpDelay(100)
            el_tracker.stopRecording()

        el_tracker.setOfflineMode()
        el_tracker.sendCommand('clear_screen 0')
        pylink.msecDelay(500)
        el_tracker.closeDataFile()

        if win is not None:
            msg = visual.TextStim(win,
                                   text='Downloading EDF from EyeLink Host PC...',
                                   color='white', height=30)
            msg.draw()
            win.flip()

        local_edf = os.path.join(session_folder, local_edf_name + '.EDF')
        try:
            el_tracker.receiveDataFile(edf_file, local_edf)
            print(f"EDF saved to: {local_edf}")
        except RuntimeError as err:
            print(f"ERROR downloading EDF: {err}")

        el_tracker.close()

    close_vpixx()

    if win is not None:
        win.close()

    core.quit()
    sys.exit()


# =============================================================================
# TRIAL EXECUTION
# =============================================================================

def run_trial(trial_cfg, block_num, overall_trial, trial_in_block, is_training,
              win, fixation, cue_left, cue_right, blink_text,
              feedback_miss, feedback_wrong, trigger_patch,
              standard_sound, deviant_sound,
              el_tracker, info,
              tones_log, presses_log, all_presses_global):
    """Run one full trial (fixation -> cue -> tones -> response -> feedback -> BLINK).

    Presses are drained at strategic points inside the trial:
      - Start of trial: sweep out any inter-trial presses (logged as
        context='inter_trial').
      - After the response window: catch responses to this trial.
      - After the BLINK: catch anything else before the next fixation.

    Returns a trial-level result dict.
    """
    context_tag = 'training' if is_training else f'block_{block_num}'

    # -------------------------------------------------------------------
    # 0. Drain any leftover presses from the previous trial's tail
    #    and log them with an inter-trial context tag.
    # -------------------------------------------------------------------
    for ev in drain_din_log(info['myLog']):
        if ev['kind'] == 'press':
            presses_log.append({
                'context':       'inter_trial',
                'overall_trial': overall_trial,
                'block':         context_tag,
                'kind':          ev['kind'],
                'label':         ev['label'],
                'hw_time':       f"{ev['hw_time']:.6f}",
            })
            all_presses_global.append((ev['label'], ev['hw_time']))

    # Check for experimenter abort key.
    if event.getKeys(keyList=['escape']):
        return {'aborted': True}

    # -------------------------------------------------------------------
    # 1. Fixation (1500 ms)  --  no trigger
    # -------------------------------------------------------------------
    fixation.draw()
    trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
    trigger_patch.draw()
    fixation_onset = win.flip()
    el_tracker.sendMessage(f'TRIALID {overall_trial}')
    el_tracker.sendMessage('fixation_onset')

    core.wait(FIXATION_DURATION)

    # -------------------------------------------------------------------
    # 2. Cue (500 ms)  --  trigger = cue direction
    # -------------------------------------------------------------------
    cue_hand = trial_cfg['cue_hand']
    cue_stim = cue_left if cue_hand == 'left' else cue_right
    cue_trigger_value = (TRIGGER_CUE_LEFT if cue_hand == 'left'
                          else TRIGGER_CUE_RIGHT)

    cue_stim.draw()
    trigger_patch.fillColor = trigger_color(cue_trigger_value)
    trigger_patch.draw()

    el_msg = f'cue_onset_{cue_hand}'
    win.callOnFlip(el_tracker.sendMessage, el_msg)
    cue_onset    = win.flip()
    cue_hw_onset = dp.DPxGetTime()

    core.wait(CUE_DURATION)

    # Reset trigger during transition to first tone.
    fixation.draw()
    trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
    trigger_patch.draw()
    win.flip()

    # -------------------------------------------------------------------
    # 3. Auditory sequence: n_standards standards, then 1 deviant
    # -------------------------------------------------------------------
    n_std = trial_cfg['n_standards']
    isis  = trial_cfg['isis']

    first_tone_hw_onset = None
    deviant_hw_onset    = None

    for tone_index in range(n_std + 1):
        is_deviant = (tone_index == n_std)
        kind       = 'deviant' if is_deviant else 'standard'

        # Pick which PsychoPy Sound object to play this tone.
        tone_stim = deviant_sound if is_deviant else standard_sound

        # Prep visual: fixation + trigger pixel
        fixation.draw()
        trig_val = TRIGGER_DEVIANT if is_deviant else TRIGGER_STANDARD
        trigger_patch.fillColor = trigger_color(trig_val)
        trigger_patch.draw()

        # Send EyeLink message at flip
        el_msg = f"{kind}_onset"
        win.callOnFlip(el_tracker.sendMessage, el_msg)

        # Schedule audio playback. On the PTB backend, preschedule to
        # hit the next vsync (sub-ms precision): PTB knows the target
        # time and plans buffer submission around it. On any other
        # backend, fall back to win.callOnFlip(tone_stim.play), which
        # starts audio at the next audio-callback boundary after flip.
        if _IS_PTB_BACKEND:
            try:
                when_ptb = win.getFutureFlipTime(clock='ptb')
                tone_stim.play(when=when_ptb)
            except Exception:
                # Belt-and-braces: if PTB scheduling fails for any
                # reason at trial time, still get audio via callOnFlip.
                win.callOnFlip(tone_stim.play)
        else:
            win.callOnFlip(tone_stim.play)

        # Flip unblocks at vsync: MEG trigger edge fires from the
        # framebuffer. On PTB the audio starts at (approximately) this
        # same instant; on other backends within a few ms.
        tone_onset    = win.flip()
        tone_hw_onset = dp.DPxGetTime()

        # Record positions for MEG alignment and later analysis
        if tone_index == 0:
            first_tone_hw_onset = tone_hw_onset
        if is_deviant:
            deviant_hw_onset = tone_hw_onset

        # Tone duration (visual trigger stays high across the tone)
        core.wait(TONE_DURATION)

        # Now that playback has begun (and, at TONE_DURATION seconds
        # in, largely completed), the backend's status is populated.
        # Query it for the reported requested/actual start times. On
        # PTB these are RequestedStartTime and StartTime in the PTB
        # clock; on other backends both will be None.
        pp_audio_requested, pp_audio_actual = get_audio_status(tone_stim)

        # NOW build the tones_log entry (all info known)
        isi_after = isis[tone_index] if tone_index < n_std else 0.0
        tones_log.append({
            'overall_trial':      overall_trial,
            'block':              context_tag,
            'trial_in_block':     trial_in_block,
            'tone_index':         tone_index + 1,
            'kind':               kind,
            'frequency':          DEVIANT_FREQ if is_deviant else STANDARD_FREQ,
            'psychopy_onset':     f"{tone_onset:.6f}",
            'hw_onset':           f"{tone_hw_onset:.6f}",
            'pp_audio_requested': f"{pp_audio_requested:.6f}" if pp_audio_requested is not None else '',
            'pp_audio_actual':    f"{pp_audio_actual:.6f}"    if pp_audio_actual is not None else '',
            'isi_after':          f"{isi_after:.4f}" if isi_after else '',
        })

        # Reset trigger during ISI (or transition to response window)
        fixation.draw()
        trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
        trigger_patch.draw()
        win.flip()

        # ISI (skip after deviant -- next phase is response window)
        if not is_deviant:
            core.wait(isi_after)

    # -------------------------------------------------------------------
    # 4. Response window (1000 ms of fixation)  --  no trigger
    # -------------------------------------------------------------------
    el_tracker.sendMessage('response_window_onset')
    core.wait(RESPONSE_WINDOW)

    # -------------------------------------------------------------------
    # 5. Drain the DIN log and classify this trial's response
    # -------------------------------------------------------------------
    trial_events = drain_din_log(info['myLog'])

    # Log every event to the raw presses CSV
    for ev in trial_events:
        if ev['kind'] in ('press', 'unknown'):
            presses_log.append({
                'context':       'trial',
                'overall_trial': overall_trial,
                'block':         context_tag,
                'kind':          ev['kind'],
                'label':         ev['label'],
                'hw_time':       f"{ev['hw_time']:.6f}",
            })
            if ev['kind'] == 'press':
                all_presses_global.append((ev['label'], ev['hw_time']))

    # Classify: find the first VALID press in the response window
    resp_min_hw = deviant_hw_onset + RESP_WIN_MIN
    resp_max_hw = deviant_hw_onset + RESP_WIN_MAX

    response_button    = None
    response_hw_time   = None
    rt                 = float('nan')
    outcome            = 'miss'

    for ev in trial_events:
        if ev['kind'] != 'press':
            continue
        if resp_min_hw <= ev['hw_time'] <= resp_max_hw:
            response_button  = ev['label']
            response_hw_time = ev['hw_time']
            rt = response_hw_time - deviant_hw_onset
            expected = EXPECTED_BUTTONS[cue_hand]
            outcome = 'correct' if response_button == expected else 'wrong_button'
            break   # first in-window press defines the response

    el_tracker.sendMessage(f'trial_outcome {outcome}')

    # -------------------------------------------------------------------
    # 6. Feedback (400 ms, errors only)
    # -------------------------------------------------------------------
    feedback_shown = False
    if outcome != 'correct':
        feedback_shown = True
        fb_stim = feedback_miss if outcome == 'miss' else feedback_wrong
        fb_stim.draw()
        trigger_patch.fillColor = trigger_color(TRIGGER_FEEDBACK)
        trigger_patch.draw()

        el_msg = f'feedback_onset_{outcome}'
        win.callOnFlip(el_tracker.sendMessage, el_msg)
        win.flip()

        core.wait(FEEDBACK_DURATION)

        # Reset trigger
        fixation.draw()
        trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
        trigger_patch.draw()
        win.flip()

    # -------------------------------------------------------------------
    # 7. BLINK trial (500 ms text)
    # -------------------------------------------------------------------
    blink_text.draw()
    trigger_patch.fillColor = trigger_color(TRIGGER_BLINK)
    trigger_patch.draw()
    win.callOnFlip(el_tracker.sendMessage, 'blink_cue')
    blink_onset = win.flip()

    core.wait(BLINK_DURATION)

    # Reset trigger (fixation for the transition into next trial)
    fixation.draw()
    trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
    trigger_patch.draw()
    win.flip()

    # -------------------------------------------------------------------
    # 8. Build the trial result
    # -------------------------------------------------------------------
    result = {
        'aborted':             False,
        'overall_trial':       overall_trial,
        'block':               context_tag,
        'trial_in_block':      trial_in_block,
        'is_training':         is_training,
        'cue_hand':            cue_hand,
        'expected_button':     EXPECTED_BUTTONS[cue_hand],
        'n_standards':         n_std,
        'fixation_onset':      f"{fixation_onset:.6f}",
        'cue_onset':           f"{cue_onset:.6f}",
        'cue_hw_onset':        f"{cue_hw_onset:.6f}",
        'first_tone_hw_onset': f"{first_tone_hw_onset:.6f}",
        'deviant_hw_onset':    f"{deviant_hw_onset:.6f}",
        'response_button':     response_button if response_button else '',
        'response_hw_time':    f"{response_hw_time:.6f}" if response_hw_time else '',
        'rt':                  f"{rt:.4f}" if not np.isnan(rt) else '',
        'outcome':             outcome,
        'feedback_shown':      feedback_shown,
        'blink_onset':         f"{blink_onset:.6f}",
    }
    return result


# =============================================================================
# MAIN
# =============================================================================

# --- Participant info dialog ---
exp_info = {'participant': '', 'session': '001'}
dlg = gui.DlgFromDict(dictionary=exp_info,
                      title='Active Oddball (FT cued)',
                      order=['participant', 'session'])
if not dlg.OK:
    core.quit()

exp_info['date'] = data.getDateStr()

results_folder = 'results'
os.makedirs(results_folder, exist_ok=True)

sub = exp_info['participant'].replace('-', '').replace('_', '')
ses = exp_info['session'].replace('-', '').replace('_', '')
edf_fname = f"s{sub}s{ses}"[:8] + '.EDF'
local_edf_name = (f"sub-{exp_info['participant']}"
                  f"_ses-{exp_info['session']}_task-oddballftcuedpypsych")

session_folder = os.path.join(results_folder, local_edf_name)
os.makedirs(session_folder, exist_ok=True)

filename_base = os.path.join(session_folder, local_edf_name)

# CSV file paths (rewritten cumulatively at each flush)
trials_csv_path  = filename_base + '_trials.csv'
tones_csv_path   = filename_base + '_tones.csv'
presses_csv_path = filename_base + '_presses.csv'


# --- VPIXX init ---
init_vpixx()


# --- EyeLink init ---
el_tracker = connect_eyelink(DUMMY_MODE, edf_fname)


# --- Window ---
win = visual.Window(
    fullscr=True,
    color=[0, 0, 0],
    colorSpace='rgb255',
    units='pix',
    allowGUI=False,
    screen=0,
)
win_w, win_h = win.size
scn_width  = int(win_w)
scn_height = int(win_h)

configure_eyelink(el_tracker, scn_width, scn_height, DUMMY_MODE)


# --- Stimuli ---
fixation = visual.ShapeStim(
    win,
    vertices=((0, -15), (0, 15), (0, 0), (-15, 0), (15, 0)),
    lineWidth=3, closeShape=False,
    lineColor='white', colorSpace='named',
)

# Cue: fixation cross flanked by arrows (matches FT figure exactly).
# Rendered as a single TextStim for simplicity ('>+>' or '<+<').
cue_left = visual.TextStim(
    win, text='<   +   <', color='white', height=60,
)
cue_right = visual.TextStim(
    win, text='>   +   >', color='white', height=60,
)

# Feedback stimuli: red text on black.
feedback_miss = visual.TextStim(
    win, text='MISS', color='red', height=80, bold=True,
)
feedback_wrong = visual.TextStim(
    win, text='WRONG BUTTON', color='red', height=60, bold=True,
)

# BLINK text: white on black (matches FT figure).
blink_text = visual.TextStim(
    win, text='BLINK', color='white', height=60, bold=True,
)

# Trigger pixel: 1x1 patch in the upper-left corner.
trigger_x = -win_w / 2.0 + TRIGGER_PATCH_SIZE / 2.0
trigger_y =  win_h / 2.0 - TRIGGER_PATCH_SIZE / 2.0
trigger_patch = visual.Rect(
    win,
    width=TRIGGER_PATCH_SIZE, height=TRIGGER_PATCH_SIZE,
    pos=(trigger_x, trigger_y),
    lineWidth=0,
    fillColor=trigger_color(TRIGGER_RESET),
    fillColorSpace='rgb',
    lineColor=trigger_color(TRIGGER_RESET),
    lineColorSpace='rgb',
)


# --- Build tones and wrap in PsychoPy Sound objects ---
standard_wave = make_tone(STANDARD_FREQ, TONE_DURATION,
                          AUDIO_SAMPLE_RATE, RAMP_DURATION)
deviant_wave  = make_tone(DEVIANT_FREQ,  TONE_DURATION,
                          AUDIO_SAMPLE_RATE, RAMP_DURATION)

# stereo=False -> the same signal goes to both channels via the
# audio backend's mono handling.
standard_sound = sound.Sound(value=standard_wave,
                              sampleRate=AUDIO_SAMPLE_RATE,
                              stereo=False)
deviant_sound  = sound.Sound(value=deviant_wave,
                              sampleRate=AUDIO_SAMPLE_RATE,
                              stereo=False)

# Detect which audio backend PsychoPy loaded. PTB supports precise
# prescheduling via play(when=T); other backends fall back to
# callOnFlip(sound.play). The detection is done once at experiment
# start and stashed on the sound objects for run_trial to consult.
_backend_module = type(standard_sound).__module__
_IS_PTB_BACKEND = 'backend_ptb' in _backend_module
print(f"Audio backend module : {_backend_module}")
print(f"PTB prescheduling    : {'ENABLED' if _IS_PTB_BACKEND else 'DISABLED (falling back to callOnFlip)'}")


# --- Generate block sequences ---
# Fresh RNG per block (no cross-block seeding).
training_seq = generate_block_sequence(
    N_TRAINING_TRIALS, MIN_STANDARDS, MAX_STANDARDS, ISI_MIN, ISI_MAX
) if RUN_TRAINING else []

block_seqs = [
    generate_block_sequence(N_TRIALS_PER_BLOCK, MIN_STANDARDS, MAX_STANDARDS,
                             ISI_MIN, ISI_MAX)
    for _ in range(N_BLOCKS)
]

# Estimated session duration (rough; ignores response feedback probability)
mean_tones      = (MIN_STANDARDS + MAX_STANDARDS) / 2 + 1
mean_isi        = (ISI_MIN + ISI_MAX) / 2
mean_tone_phase = mean_tones * TONE_DURATION + (mean_tones - 1) * mean_isi
per_trial_est   = (FIXATION_DURATION + CUE_DURATION + mean_tone_phase +
                   RESPONSE_WINDOW + BLINK_DURATION)
main_trials     = N_BLOCKS * N_TRIALS_PER_BLOCK
est_min         = main_trials * per_trial_est / 60.0
print(f"Estimated main recording time: ~{est_min:.1f} min "
      f"({N_BLOCKS} blocks x {N_TRIALS_PER_BLOCK} trials)")


# --- EyeLink calibration ---
genv = EyeLinkCoreGraphicsPsychoPy(el_tracker, win)
genv.setCalibrationColors((1, 1, 1), (-1, -1, -1))
genv.setTargetType('circle')
genv.setTargetSize(24)
genv.setCalibrationSounds('', '', '')
pylink.openGraphicsEx(genv)

cal_msg = visual.TextStim(
    win,
    text=("Before we begin, we need to calibrate the eye tracker.\n\n"
          "A dot will appear at various locations on the screen.\n"
          "Follow the dot with your eyes; do not anticipate its next\n"
          "location.\n\n"
          "Experimenter: press ENTER to begin calibration."),
    color='white', height=28, wrapWidth=900,
)
cal_msg.draw()
win.flip()
event.waitKeys(keyList=['return'])

if not DUMMY_MODE:
    try:
        el_tracker.doTrackerSetup()
    except RuntimeError as err:
        print(f"ERROR in tracker setup: {err}")
        el_tracker.exitCalibration()


# --- Drift check + start recording + start DIN log ---
if not DUMMY_MODE:
    while True:
        if (not el_tracker.isConnected()) or el_tracker.breakPressed():
            terminate_task(win, el_tracker, edf_fname, session_folder,
                            local_edf_name, DUMMY_MODE)
        try:
            err = el_tracker.doDriftCorrect(int(scn_width / 2),
                                             int(scn_height / 2), 1, 1)
            if err is not pylink.ESC_KEY:
                break
        except Exception:
            pass

el_tracker.setOfflineMode()
try:
    el_tracker.startRecording(1, 1, 1, 1)
except RuntimeError as err:
    print(f"ERROR starting recording: {err}")
    terminate_task(win, el_tracker, edf_fname, session_folder,
                    local_edf_name, DUMMY_MODE)

pylink.pumpDelay(100)
el_tracker.sendMessage('EXPERIMENT_START')

# Start the DIN log ONCE.  Never pause/resume.
info = {'myLog': dp.DPxSetDinLog(int(12e6), 500)}
dp.DPxStartDinLog()
dp.DPxUpdateRegCache()

# Data containers -- flushed to CSV at every block boundary
trials_log         = []   # list of dicts, one per trial
tones_log          = []   # list of dicts, one per tone
presses_log        = []   # list of dicts, one per DIN event
all_presses_global = []   # (label, hw_time) tuples for in-memory scoring


# --- Instructions ---
instr = visual.TextStim(
    win,
    text=("You will hear a series of tones.\n\n"
          "On each trial an arrow cue appears:\n"
          "    <  +  <  = LEFT hand    ->  +  > = RIGHT hand\n\n"
          "After the cue you will hear several identical tones,\n"
          "followed by ONE different (higher) tone.\n\n"
          "As soon as you hear the DIFFERENT tone,\n"
          "press the INDEX FINGER button on the cued hand\n"
          "as quickly as possible.\n\n"
          "If you miss or press the wrong button, you'll see feedback.\n\n"
          "When 'BLINK' appears, you may blink freely.\n"
          "Otherwise please try not to blink and hold your gaze on the cross.\n\n"
          "Experimenter: press SPACE to start the training block."),
    color='white', height=26, wrapWidth=1000,
)
instr.draw()
win.flip()
keys = event.waitKeys(keyList=['space', 'escape'])
if 'escape' in keys:
    terminate_task(win, el_tracker, edf_fname, session_folder,
                    local_edf_name, DUMMY_MODE)

fixation.draw()
trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
trigger_patch.draw()
win.flip()
core.wait(2.0)


# =============================================================================
# TRAINING BLOCK
# =============================================================================

overall_trial = 0
aborted = False

if RUN_TRAINING and training_seq:
    el_tracker.sendMessage('TRAINING_START')

    for t_in_block, cfg in enumerate(training_seq, start=1):
        overall_trial += 1  # training trials counted in overall_trial for
                            # bookkeeping but is_training flag distinguishes them
        el_tracker.sendCommand(
            f"record_status_message 'TRAINING {t_in_block}/{N_TRAINING_TRIALS}'"
        )
        result = run_trial(
            cfg, block_num=0, overall_trial=overall_trial,
            trial_in_block=t_in_block, is_training=True,
            win=win, fixation=fixation, cue_left=cue_left, cue_right=cue_right,
            blink_text=blink_text,
            feedback_miss=feedback_miss, feedback_wrong=feedback_wrong,
            trigger_patch=trigger_patch,
            standard_sound=standard_sound, deviant_sound=deviant_sound,
            el_tracker=el_tracker, info=info,
            tones_log=tones_log, presses_log=presses_log,
            all_presses_global=all_presses_global,
        )
        if result.get('aborted'):
            aborted = True
            break
        trials_log.append(result)

    el_tracker.sendMessage('TRAINING_END')

    # Flush after training
    if not aborted:
        write_trials_csv(trials_csv_path,  trials_log)
        write_tones_csv (tones_csv_path,   tones_log)
        write_presses_csv(presses_csv_path, presses_log)

    # Training -> main experiment transition (only if training happened)
    if not aborted and RUN_TRAINING and training_seq:
        # Show a transition screen and require experimenter SPACE.
        # Then re-do a drift check so the main experiment starts with
        # good calibration.
        training_correct = sum(1 for t in trials_log
                                if t.get('is_training')
                                and t.get('outcome') == 'correct')
        training_total = len(training_seq)
        tr_pct = 100.0 * training_correct / training_total if training_total > 0 else 0.0

        transition = visual.TextStim(
            win,
            text=(f"Training complete.\n\n"
                  f"Correct: {training_correct}/{training_total} ({tr_pct:.1f}%)\n\n"
                  f"The main experiment will now begin.\n"
                  f"{N_BLOCKS} blocks of {N_TRIALS_PER_BLOCK} trials each,\n"
                  f"with breaks between blocks.\n\n"
                  "Experimenter: press SPACE to start the main experiment."),
            color='white', height=28, wrapWidth=1000,
        )
        transition.draw()
        win.flip()
        keys = event.waitKeys(keyList=['space', 'escape'])
        if 'escape' in keys:
            aborted = True

        if not aborted:
            do_drift_check_between_blocks(el_tracker, scn_width, scn_height,
                                           DUMMY_MODE)
            # Reset the overall_trial counter so main-experiment trials
            # are numbered 1..N_MAIN and are cleanly separable from
            # training in the CSV.
            overall_trial = 0


# =============================================================================
# BREAK SCREEN HELPER (defined here because it uses `win`, `event`, etc.)
# =============================================================================

def show_break_screen(block_completed, block_correct, block_total):
    """Show the between-block break screen and wait for experimenter SPACE.

    Enforces a minimum rest of INTERBLOCK_MIN_REST seconds before SPACE
    is accepted (subject gets a real break; experimenter can't rush past).
    """
    pct = 100.0 * block_correct / block_total if block_total > 0 else 0.0
    remaining = INTERBLOCK_MIN_REST

    while remaining > 0:
        msg = (
            f"Block {block_completed} of {N_BLOCKS} complete.\n\n"
            f"Correct: {block_correct}/{block_total} ({pct:.1f}%)\n\n"
            f"Rest for a moment.\n"
            f"Please stay still.\n\n"
            f"Experimenter: SPACE available in {remaining:.0f} s"
        )
        break_stim = visual.TextStim(
            win, text=msg, color='white', height=32, wrapWidth=1000,
        )
        break_stim.draw()
        win.flip()
        core.wait(1.0)
        remaining -= 1.0
        if event.getKeys(keyList=['escape']):
            return 'abort'

    # Enable SPACE
    while True:
        msg = (
            f"Block {block_completed} of {N_BLOCKS} complete.\n\n"
            f"Correct: {block_correct}/{block_total} ({pct:.1f}%)\n\n"
            f"Rest for a moment.\n"
            f"Please stay still.\n\n"
            f"Experimenter: press SPACE to continue"
        )
        break_stim = visual.TextStim(
            win, text=msg, color='white', height=32, wrapWidth=1000,
        )
        break_stim.draw()
        win.flip()
        keys = event.waitKeys(keyList=['space', 'escape'])
        if 'escape' in keys:
            return 'abort'
        if 'space' in keys:
            return 'continue'


# =============================================================================
# MAIN BLOCKS
# =============================================================================

if not aborted:
    for block_i, seq in enumerate(block_seqs, start=1):
        el_tracker.sendMessage(f'BLOCK_START {block_i}')

        block_correct = 0
        block_total   = 0

        for t_in_block, cfg in enumerate(seq, start=1):
            overall_trial += 1
            el_tracker.sendCommand(
                f"record_status_message "
                f"'BLOCK {block_i}/{N_BLOCKS} TRIAL {t_in_block}/{N_TRIALS_PER_BLOCK}'"
            )

            result = run_trial(
                cfg, block_num=block_i, overall_trial=overall_trial,
                trial_in_block=t_in_block, is_training=False,
                win=win, fixation=fixation, cue_left=cue_left, cue_right=cue_right,
                blink_text=blink_text,
                feedback_miss=feedback_miss, feedback_wrong=feedback_wrong,
                trigger_patch=trigger_patch,
                standard_sound=standard_sound, deviant_sound=deviant_sound,
                el_tracker=el_tracker, info=info,
                tones_log=tones_log, presses_log=presses_log,
                all_presses_global=all_presses_global,
            )
            if result.get('aborted'):
                aborted = True
                el_tracker.sendMessage(f'EXPERIMENT_ABORTED trial {overall_trial}')
                break

            trials_log.append(result)
            block_total += 1
            if result['outcome'] == 'correct':
                block_correct += 1

        el_tracker.sendMessage(f'BLOCK_END {block_i}')

        # Flush CSVs (crash-safe)
        write_trials_csv(trials_csv_path,  trials_log)
        write_tones_csv (tones_csv_path,   tones_log)
        write_presses_csv(presses_csv_path, presses_log)

        if aborted:
            break

        # Break screen + drift check (skip after final block)
        if block_i < N_BLOCKS:
            result = show_break_screen(block_i, block_correct, block_total)
            if result == 'abort':
                aborted = True
                el_tracker.sendMessage(f'EXPERIMENT_ABORTED break {block_i}')
                break
            do_drift_check_between_blocks(el_tracker, scn_width, scn_height,
                                           DUMMY_MODE)


# =============================================================================
# END OF EXPERIMENT
# =============================================================================

el_tracker.sendMessage('EXPERIMENT_END')

# One last drain of the DIN log in case of trailing presses
for ev in drain_din_log(info['myLog']):
    if ev['kind'] == 'press':
        presses_log.append({
            'context':       'end',
            'overall_trial': overall_trial,
            'block':         'end',
            'kind':          ev['kind'],
            'label':         ev['label'],
            'hw_time':       f"{ev['hw_time']:.6f}",
        })

# Final flush
write_trials_csv(trials_csv_path,  trials_log)
write_tones_csv (tones_csv_path,   tones_log)
write_presses_csv(presses_csv_path, presses_log)

print(f"Trials CSV : {trials_csv_path}")
print(f"Tones CSV  : {tones_csv_path}")
print(f"Presses CSV: {presses_csv_path}")

pylink.pumpDelay(100)
if not DUMMY_MODE and el_tracker.isConnected():
    el_tracker.stopRecording()
dp.DPxStopDinLog()
dp.DPxUpdateRegCache()


# --- Overall summary ---
main_trials = [t for t in trials_log if not t['is_training']]
n_main      = len(main_trials)
n_correct   = sum(1 for t in main_trials if t['outcome'] == 'correct')
n_wrong     = sum(1 for t in main_trials if t['outcome'] == 'wrong_button')
n_miss      = sum(1 for t in main_trials if t['outcome'] == 'miss')

pct_correct = 100.0 * n_correct / n_main if n_main > 0 else 0.0
correct_rts = [float(t['rt']) for t in main_trials
               if t['outcome'] == 'correct' and t['rt'] != '']
mean_rt = np.mean(correct_rts) if correct_rts else float('nan')

summary_lines = [
    "=== PERFORMANCE SUMMARY (main experiment) ===",
    f"Correct:      {n_correct}/{n_main} ({pct_correct:.1f}%)",
    f"Wrong button: {n_wrong}",
    f"Miss:         {n_miss}",
]
if correct_rts:
    summary_lines.append(f"Mean RT (correct): {mean_rt*1000:.0f} ms")
summary_str = "\n".join(summary_lines)
print("\n" + summary_str)

# End screen
end_msg = visual.TextStim(
    win,
    text=("The experiment is complete.\n\n"
          + summary_str.replace("=== ", "").replace(" ===", "")
          + "\n\nThank you!\n\nExperimenter: press SPACE to exit."),
    color='white', height=26, wrapWidth=1000,
)
end_msg.draw()
win.flip()
event.waitKeys(keyList=['space', 'escape'])

terminate_task(win, el_tracker, edf_fname, session_folder,
                local_edf_name, DUMMY_MODE)
