#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Active Auditory Oddball, FieldTrip Cued Paradigm
(VPIXX audio + keyboard responses)
========================================================================

OVERVIEW
--------
Bimanual cued active oddball. Replicates the FieldTrip tutorial
paradigm (Oostenveld et al.), documented at
www.fieldtriptoolbox.org/workshop/natmeg2014/meg_audodd/.
Each trial cues the subject to prepare a left- or right-hand response,
presents 3-7 standard tones followed by 1 deviant tone, and requires a
button press with the cued index finger. Supports classical MMN/P3
analysis on tone-locked ERFs and lateralized post-movement beta rebound
(PMBR) analysis on the cued-hand contrast.

Audio is hardware-scheduled by the DATAPixx3 and vsync-locked to the
MEG trigger pixel. Responses come from a Current Designs button box
that presents itself as an HID keyboard. Eye tracking runs on the
EyeLink Host PC throughout.

For local testing without hardware, the startup GUI offers
`dummy_eyelink` and `dummy_vpixx` checkboxes. Either can also be
auto-forced on when the corresponding library (pylink / pypixxlib)
isn't installed. In dummy_vpixx mode audio falls back to PsychoPy
sound (audible but not vsync-locked), and *_vp / *_vp_est columns
in the CSVs are left blank to make the dummy run distinguishable
from a real one.

Structure (one trial = one cycle of the figure):

    +-----------+-----+-----------------+---------+----------+-------+
    | fixation  | cue | auditory stim   | resp.   | feedback | BLINK |
    |  1500 ms  |500ms|  4000-8800 ms   | 1000 ms |  400 ms  | 500 ms|
    |     +     | >+> | tones + oddball |    +    |  (errors |       |
    |           | or  |                 |         |   only)  |       |
    |           | <+< |                 |         |          |       |
    +-----------+-----+-----------------+---------+----------+-------+

Three blocks x 100 trials = 300 trials total, ~51 minutes recording,
plus a ~3-minute training block at the start.


AUDIO STIMULI VIA VPIXX AUDIO SUBSYSTEM
---------------------------------------
Tones are generated as int16 arrays at experiment start and loaded
into DATAPixx3 RAM. Audio onset is hardware-locked to the video vsync
via DPxWriteRegCacheAfterVideoSync: the same vsync that triggers VPIXX
to read the trigger pixel and put it on DOUT (MEG trigger edge) also
pushes the audio-schedule start bit to the device.

Per-tone sequence:

    1. prep_tone_schedule(kind)
       Configure the schedule (DPxSetAudioSchedule) and push it to
       the device (DPxWriteRegCache). Config resident; start bit
       NOT yet armed.

    2. Draw the visual frame (fixation + trigger pixel).

    3. Immediately before flip:
         DPxStartAudSched                  arm start bit (local reg)
         DPxWriteRegCacheAfterVideoSync    queue push at next vsync

    4. win.flip()
       Blocks until that vsync. At that vsync:
         - VPIXX reads the trigger pixel color from the framebuffer
           and puts it on DOUT -> MEG trigger channel edge rises
         - Queued register push executes -> audio playback begins

    5. DPxGetTime -> capture the hardware timestamp of the vsync.

Audio playback and MEG trigger edge fire at the same vsync with no
software offset between them. The only remaining delay in the auditory
pathway is the physical transit through the OPM headphone tubes (or
loudspeaker-to-ear) - a constant acoustic latency to measure once with
a microphone and subtract from MMN peak latencies in analysis.

IMPORTANT INVARIANT: between prep_tone_schedule and the DPxStartAudSched
+ DPxWriteRegCacheAfterVideoSync pair, no other code may call
DPxUpdateRegCache (which reads device state into the local register
cache and would clobber a pending start bit).


TRIGGER SCHEME (VPIXX Pixel Mode B, blue channel only)
------------------------------------------------------
Sent by drawing a 1x1 patch in the upper-left corner:

    standard tone onset:   1   (Trigger 1)
    deviant tone onset:    2   (Trigger 2)
    blink cue onset:       4   (Trigger 3)
    left cue onset:        8   (Trigger 4)
    right cue onset:      16   (Trigger 5)
    error feedback onset: 32   (Trigger 6)
    (reset between events: 0)

Response events are not pixel-triggered; see KEYBOARD INPUT below.


TRIGGER vs. PERCEIVED-STIMULUS TIMING
-------------------------------------
All pixel-mode triggers fire at the vsync when win.flip() unblocks.
That vsync marks when the display BEGINS drawing the new frame from
the top; the pixels the subject actually sees are illuminated one
frame later (~8.33 ms at 120 Hz). The trigger therefore LEADS the
perceived visual stimulus by one frame. When locking analyses to the
moment the subject actually saw the stimulus, subtract DISPLAY_FRAME_MS
from the trigger-channel edge time.

    Event                   MEG trigger edge -> subject perceives
    -----------------------  --------------------------------------
    Standard / deviant tone  + transit_delay (measure on setup)
    Cue arrow                + one video frame (DISPLAY_FRAME_MS)
    BLINK text               + one video frame
    Error feedback           + one video frame


KEYBOARD INPUT
--------------
The button box emits standard USB HID keyboard events. Polling is via
psychopy.hardware.keyboard.Keyboard. Response times are in the
PsychoPy default clock, so RTs are computed as
`response_time_pp - deviant_onset_pp`.

Populate KEY_CODES (in the parameters section) with the mapping from
key names (as emitted by the button box) to finger labels. Common
Current Designs default outputs are digits '1'-'9' or letters 'a'-'z';
check the box's config utility. The script validates KEY_CODES at
startup and exits if 'left_index' and 'right_index' are not both
defined; other finger positions are optional.

Definitive response timing for MEG analysis should be read from the
button box's TTL wiring to the MEG trigger channel, not from these
keyboard timestamps: the OS HID pipeline carries a few ms of jitter
that is fine for behavior but not for tight MEG locking.


RESPONSE SCORING
----------------
Valid response window: 150-1400 ms after deviant onset (150 ms floor
rejects anticipation; 1400 ms ceiling = deviant duration + response
phase, matching the FieldTrip task).

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


OUTPUT FILES
------------
results/sub-<p>_ses-<s>_task-oddballftcued/

    ..._trials.csv    one row per trial (main behavioral log)
    ..._tones.csv     one row per tone (per-tone vpixx timestamps)
    ..._presses.csv   one row per detected button-box event
    ....EDF           EyeLink data (from Host PC at experiment end)


PRE-FLIGHT CHECKLIST
--------------------
    1. VPIXX device is on and reachable (DPxOpen succeeds), or check
       `dummy_vpixx` in the startup dialog to run without it.
    2. VPIXX is running Pixel Mode B (this script enables it).
    3. Audio set to desired path (headphones or loudspeakers) and
       volume sufficient.
    4. Button box is reporting keyboard events. Open any text field,
       press each button, note what key each finger emits, and fill
       in KEY_CODES accordingly.
    5. Button box TTL trigger output is wired into the MEG trigger
       channel.
    6. EyeLink Host PC at 100.1.1.1, or check `dummy_eyelink` in the
       startup dialog to skip it.
    7. Audio transit delay measured; record in experiment metadata
       for MMN latency correction.
"""

# =============================================================================
# IMPORTS
# =============================================================================

import os
import sys
import csv
import json

import numpy as np

from psychopy import visual, core, event, gui, data, logging
from psychopy.hardware import keyboard
# pylink and EyeLinkCoreGraphicsPsychoPy are required dependencies to eye
# track. If they're not installed, DUMMY_MODE (EyeLink) is auto-forced on
# after the startup GUI and stand-in mocks are installed, so the paradigm
# runs end-to-end without eye tracking. In normal (non-dummy) mode with
# the libraries installed, the real EyeLink connection is used.
try:
    import pylink
    from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy
    _HAS_PYLINK = True
except ImportError:
    pylink = None
    EyeLinkCoreGraphicsPsychoPy = None
    _HAS_PYLINK = False

# pypixxlib is a required dependency for high-precision VPIXX audio
# delivery. In DUMMY_VPIXX mode we install a no-op mock after the
# startup GUI. If the library isn't installed at all, we force
# DUMMY_VPIXX on and warn. The actual `dp` binding happens after the
# GUI so helper functions can reference it lazily.
try:
    from pypixxlib import _libdpx as _real_dp
    _HAS_PYPIXXLIB = True
except ImportError:
    _real_dp = None
    _HAS_PYPIXXLIB = False
dp = None

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
# so that any future combined events (currently none) would be
# OR-decodable.
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

# --- Response keys (keyboard input from Current Designs or similar box) ---
#
# Edit this dict when swapping to a different button box. The key names
# on the left must match what psychopy.hardware.keyboard reports (see
# PsychoPy key-name reference; e.g. '1', 'a', 'space', 'lshift',
# 'num_1', etc.). The finger labels on the right can be any string;
# the ones the paradigm actually scores are 'left_index' and
# 'right_index'.
#
# Minimum required entries for the paradigm to run:
#   - one key mapped to 'left_index'
#   - one key mapped to 'right_index'
# Any additional entries (other fingers) will be logged as wrong_button
# responses when pressed in the response window, which is useful for
# distinguishing "wrong finger" from "unknown key" in the CSV. Keys
# not present in KEY_CODES are ignored entirely by the response scorer.
#
# Example (uncomment and edit):
# KEY_CODES = {
#     '1': 'left_pinky',
#     '2': 'left_ring',
#     '3': 'left_middle',
#     '4': 'left_index',
#     '6': 'right_index',
#     '7': 'right_middle',
#     '8': 'right_ring',
#     '9': 'right_pinky',
# }
KEY_CODES = {
    '1': 'left_index',
    '2': 'right_index',
}

# Which button (finger label) is the correct response for each cue direction:
EXPECTED_BUTTONS = {'left': 'left_index', 'right': 'right_index'}

# Keyboard exit key (aborts the experiment when pressed).
EXIT_KEY = 'escape'

# --- VPIXX audio buffer addresses and output volume ---
# Each tone is ~19200 samples * 2 bytes = ~38 kB.  Use 500 kB spacing
# to leave plenty of room and land on round numbers.
STANDARD_BUFFER_ADDR = int(16.0e6)   # 16,000,000 (VPIXX default)
DEVIANT_BUFFER_ADDR  = int(16.5e6)   # 16,500,000

# VPIXX audio codec output volume (0.0-1.0). The codec defaults to 0.0
# on a freshly-opened device, which produces cleanly-scheduled silent
# playback with no error (a very hard silence to debug). init_vpixx()
# sets left and right volumes to this value.
VPIXX_AUDIO_VOLUME = 0.5

# --- EyeLink ---
DUMMY_MODE = False   # True skips EyeLink (development-only)
EYELINK_IP = "100.1.1.1"
CAL_TYPE   = "HV13"  # 13-point calibration

# --- VPIXX ---
# True: run without a real DATAPixx3 connected. All dp.DPx* calls become
# no-ops; audio plays through PsychoPy sound as a fallback; *_vp and
# *_vp_est columns are left blank in the CSV outputs. Useful for
# development, demos, and testing on any machine.
DUMMY_VPIXX = False


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_tone_int16(frequency, duration, sample_rate,
                    ramp_duration, amplitude=AUDIO_AMPLITUDE):
    """Generate a pure sine tone with cosine on/off ramps as int16.

    Returns a 1-D numpy array of int16 samples ready to load into the
    VPIXX audio buffer via DPxWriteAudioBuffer.
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

    # Scale to int16. amplitude in [0, 1]; int16 range is -32768..32767.
    tone = np.clip(tone * amplitude, -1.0, 1.0)
    return (tone * 32767.0).astype(np.int16)


def rgb_255_to_psychopy(rgb):
    """Convert an [R,G,B] triple in 0-255 to PsychoPy's default [-1,+1] space."""
    return [(c / 127.5) - 1.0 for c in rgb]


def trigger_color(value):
    """Return the PsychoPy fill color that sets Pixel Mode B trigger to `value`.

    Blue channel = trigger value; red and green channels = 0.
    """
    return rgb_255_to_psychopy([0, 0, value])


def _fmt_vp(val, precision=6):
    """Format a VPIXX-clock value for CSV output.

    Returns an empty string when DUMMY_VPIXX is True (mock clock has no
    meaningful value); otherwise returns the value formatted to the
    requested decimal precision. Applied to every *_vp and *_vp_est
    column so dummy-mode CSVs don't fill those cells with fake zeros.
    """
    if DUMMY_VPIXX:
        return ''
    return f"{val:.{precision}f}"


def load_tone_into_buffer(tone_int16, buffer_addr):
    """Push an int16 tone waveform into VPIXX DATAPixx3 RAM at buffer_addr."""
    dp.DPxWriteAudioBuffer(tone_int16, buffer_addr)
    dp.DPxWriteRegCache()


def prep_tone_schedule(kind):
    """Configure the VPIXX audio schedule for the standard or deviant tone.

    Sets the audio sample rate, sample count, channel mode ('mono'),
    and buffer address, then pushes the config to the device. Does NOT
    arm the start bit. Immediately before the visual flip that fires
    the tone, the caller must:

        dp.DPxStartAudSched()                # arm start bit (local reg)
        dp.DPxWriteRegCacheAfterVideoSync()  # queue push at next vsync
        win.flip()                           # audio + trigger at vsync

    Parameters
    ----------
    kind : {'standard', 'deviant'}

    Notes
    -----
    Uses `standard_n_samples` / `deviant_n_samples` from module scope
    (set at experiment start once we know how long the tones are).
    """
    if kind == 'standard':
        addr = STANDARD_BUFFER_ADDR
        n    = standard_n_samples
    else:
        addr = DEVIANT_BUFFER_ADDR
        n    = deviant_n_samples
    dp.DPxSetAudioSchedule(0.0, AUDIO_SAMPLE_RATE, n, 'mono', addr)
    dp.DPxWriteRegCache()


def get_keyboard_events(kb, key_codes, exit_key=EXIT_KEY):
    """Poll the keyboard for new events and classify them.

    Uses psychopy.hardware.keyboard.Keyboard.getKeys(), which drains
    the keyboard's internal buffer so repeated calls only return NEW
    events. Only key names present in `key_codes` (plus `exit_key`)
    are captured; other keys are ignored.

    Parameters
    ----------
    kb : psychopy.hardware.keyboard.Keyboard
        The keyboard instance created at experiment start.
    key_codes : dict
        Mapping from key name -> finger label.
    exit_key : str
        Keyboard key that aborts the experiment.

    Returns
    -------
    events : list of dict
        Each dict has:
            kind      : always 'press' (releases are not captured; only
                        key-down events are queued for our keyList)
            label     : finger label from key_codes
            key_name  : the raw keyboard key name (for debugging)
            time      : PsychoPy-clock timestamp of the key-down event
                        (same clock as win.flip() return values)
    abort : bool
        True if exit_key was pressed since the last call.
    """
    keyList = list(key_codes.keys()) + [exit_key]
    new_keys = kb.getKeys(keyList=keyList, waitRelease=False)

    events = []
    abort  = False
    for key in new_keys:
        if key.name == exit_key:
            abort = True
            continue
        label = key_codes.get(key.name)
        if label is None:
            # In keyList by construction, but not in key_codes -> ignore.
            continue
        events.append({
            'kind':     'press',
            'label':    label,
            'key_name': key.name,
            'time':     key.tDown,
        })

    return events, abort


def estimate_vp_times(events):
    """Tag each event with an approximate VPIXX-clock timestamp.

    Samples DPxGetTime and core.getTime "now" as a shared anchor,
    then converts each event's PsychoPy-clock time to VP-clock time
    by preserving the delta. Accurate to within ~one video frame
    since the anchors weren't captured at the event moment. In
    DUMMY_VPIXX mode the anchor is 0 (mock clock) and downstream
    _fmt_vp() blanks the column, so the estimation is a no-op in
    practice.

    Modifies each event dict in place, adding a 'time_vp_est' key.
    No-op if `events` is empty.
    """
    if not events:
        return
    dp.DPxUpdateRegCache()
    anchor_vp = dp.DPxGetTime()
    anchor_pp = core.getTime()
    for ev in events:
        ev['time_vp_est'] = anchor_vp + (ev['time'] - anchor_pp)


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
    """Open the VPIXX device, enable Pixel Mode B, and init the audio codec.

    Sets left/right audio volume to VPIXX_AUDIO_VOLUME; see the
    constant's comment for why that matters.
    """
    dp.DPxOpen()
    dp.DPxStopAllScheds()
    dp.DPxEnableDoutPixelModeB()   # blue-channel-only trigger output
    dp.DPxInitAudCodec()           # initialize audio subsystem
    dp.DPxSetAudLeftVolume(VPIXX_AUDIO_VOLUME)
    dp.DPxSetAudRightVolume(VPIXX_AUDIO_VOLUME)
    dp.DPxWriteRegCache()


def close_vpixx():
    """Cleanly stop schedules, disable pixel mode, and disconnect."""
    try:
        dp.DPxStopAllScheds()
    except Exception:
        pass
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
    """Write the trial-level CSV (cumulative, overwritten each flush).

    Timestamp columns are named with a clock-provenance suffix:
        *_pp        -- PsychoPy default clock (behavioral RT reference)
        *_vp        -- VPIXX DATAPixx3 hardware clock (MEG alignment)
        *_vp_est    -- Estimated VPIXX-clock time for events VPIXX did
                       not directly detect (keyboard presses). See the
                       KEYBOARD INPUT section of the module docstring
                       for how this is derived and the accuracy caveat.
    """
    fields = ['overall_trial', 'block', 'trial_in_block', 'is_training',
              'cue_hand', 'expected_button', 'n_standards',
              'fixation_onset_pp', 'fixation_onset_vp',
              'cue_onset_pp', 'cue_onset_vp',
              'first_tone_onset_pp', 'first_tone_onset_vp',
              'deviant_onset_pp', 'deviant_onset_vp',
              'response_button', 'response_key_name',
              'response_time_pp', 'response_time_vp_est',
              'rt_pp', 'rt_vp_est',
              'outcome', 'feedback_shown',
              'blink_onset_pp', 'blink_onset_vp']
    with open(filename, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def write_tones_csv(filename, rows):
    """Write the per-tone CSV (cumulative, overwritten each flush).

    Columns:
        overall_trial, block, trial_in_block, tone_index, kind, frequency
        onset_pp    - PsychoPy clock, from win.flip()
        onset_vp    - VPIXX hardware clock, from DPxGetTime()
        isi_after   - seconds until the next tone
    """
    fields = ['overall_trial', 'block', 'trial_in_block', 'tone_index',
              'kind', 'frequency', 'onset_pp', 'onset_vp',
              'isi_after']
    with open(filename, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def write_presses_csv(filename, rows):
    """Write the raw keyboard-event CSV (cumulative, overwritten each flush).

    Timestamps:
        time_pp     - PsychoPy-clock timestamp of the key-down event.
        time_vp_est - Estimated VPIXX-clock timestamp of the same event.
                      See KEYBOARD INPUT in the module docstring for
                      how this is derived and the accuracy caveat.
    """
    fields = ['context', 'overall_trial', 'block', 'kind', 'label',
              'key_name', 'time_pp', 'time_vp_est']
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
              el_tracker, kb,
              tones_log, presses_log, all_presses_global):
    """Run one full trial (fixation -> cue -> tones -> response -> feedback -> BLINK).

    Presses are drained at two strategic points inside the trial:
      - Start of trial: sweep out any leftover inter-trial presses
        (logged as context='inter_trial').
      - Every frame during the response window: catch responses to
        this trial (logged as context='trial').

    Returns a trial-level result dict.
    """
    context_tag = 'training' if is_training else f'block_{block_num}'

    # -------------------------------------------------------------------
    # 0. Drain any leftover keyboard presses from the previous trial's
    #    tail and log them with an inter-trial context tag.
    # -------------------------------------------------------------------
    inter_events, abort_key = get_keyboard_events(kb, KEY_CODES)
    if abort_key:
        return {'aborted': True}

    estimate_vp_times(inter_events)
    for ev in inter_events:
        presses_log.append({
            'context':       'inter_trial',
            'overall_trial': overall_trial,
            'block':         context_tag,
            'kind':          ev['kind'],
            'label':         ev['label'],
            'key_name':      ev['key_name'],
            'time_pp':       f"{ev['time']:.6f}",
            'time_vp_est':   _fmt_vp(ev['time_vp_est']),
        })
        all_presses_global.append((ev['label'], ev['time']))

    # -------------------------------------------------------------------
    # 1. Fixation (1500 ms)  --  no trigger
    # -------------------------------------------------------------------
    fixation.draw()
    trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
    trigger_patch.draw()
    fixation_onset_pp = win.flip()
    dp.DPxUpdateRegCache()
    fixation_onset_vp = dp.DPxGetTime()
    el_tracker.sendMessage(f'TRIALID {overall_trial}')
    el_tracker.sendMessage('fixation_onset')

    core.wait(FIXATION_DURATION)

    # -------------------------------------------------------------------
    # 2. Cue (500 ms)  --  trigger = cue direction
    # -------------------------------------------------------------------
    cue_hand = trial_cfg['cue_hand']
    cue_arrows = cue_left if cue_hand == 'left' else cue_right
    cue_trigger_value = (TRIGGER_CUE_LEFT if cue_hand == 'left'
                          else TRIGGER_CUE_RIGHT)

    # Fixation cross first (always at exact pixel (0,0)); arrows flank
    # it. This keeps the '+' from shifting between fixation-only and
    # cue frames.
    fixation.draw()
    for arrow in cue_arrows:
        arrow.draw()
    trigger_patch.fillColor = trigger_color(cue_trigger_value)
    trigger_patch.draw()

    el_msg = f'cue_onset_{cue_hand}'
    win.callOnFlip(el_tracker.sendMessage, el_msg)
    cue_onset_pp = win.flip()
    dp.DPxUpdateRegCache()
    cue_onset_vp = dp.DPxGetTime()

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

    first_tone_onset_pp = None
    first_tone_onset_vp = None
    deviant_onset_pp    = None   # PsychoPy clock; used for RT calc
    deviant_onset_vp    = None

    for tone_index in range(n_std + 1):
        is_deviant = (tone_index == n_std)
        kind       = 'deviant' if is_deviant else 'standard'

        # Configure the VPIXX audio schedule for this tone. This sets
        # the buffer address, sample count, and 'mono' mode, then
        # pushes the config to the device. Does NOT arm the start bit.
        prep_tone_schedule(kind)

        # Prep visual: fixation + trigger pixel
        fixation.draw()
        trig_val = TRIGGER_DEVIANT if is_deviant else TRIGGER_STANDARD
        trigger_patch.fillColor = trigger_color(trig_val)
        trigger_patch.draw()

        # Send EyeLink message at flip
        el_msg = f"{kind}_onset"
        win.callOnFlip(el_tracker.sendMessage, el_msg)

        # Arm audio start bit locally, then queue the register push
        # to fire on the next vsync. Between here and win.flip(),
        # nothing may call DPxUpdateRegCache (would clobber the arm).
        dp.DPxStartAudSched()
        dp.DPxWriteRegCacheAfterVideoSync()

        # In dummy mode, queue the PsychoPy fallback sound for the same
        # flip. Timing is approximate but audible for functional testing.
        if DUMMY_VPIXX:
            stim = deviant_stim if is_deviant else standard_stim
            stim.stop()
            win.callOnFlip(stim.play)

        # Flip unblocks at vsync. At that vsync:
        #   - VPIXX puts trigger byte on DOUT (MEG trigger edge)
        #   - Queued register push executes -> audio playback begins
        # Both events are aligned to the same vsync in hardware.
        tone_onset_pp = win.flip()
        dp.DPxUpdateRegCache()   # refresh so DPxGetTime returns a fresh sample
        tone_onset_vp = dp.DPxGetTime()

        # Record positions for RT / CSV / summary
        if tone_index == 0:
            first_tone_onset_pp = tone_onset_pp
            first_tone_onset_vp = tone_onset_vp
        if is_deviant:
            deviant_onset_pp = tone_onset_pp
            deviant_onset_vp = tone_onset_vp

        # Tone duration (visual trigger stays high across the tone)
        core.wait(TONE_DURATION)

        # Log tone event to CSV
        isi_after = isis[tone_index] if tone_index < n_std else 0.0
        tones_log.append({
            'overall_trial':  overall_trial,
            'block':          context_tag,
            'trial_in_block': trial_in_block,
            'tone_index':     tone_index + 1,
            'kind':           kind,
            'frequency':      DEVIANT_FREQ if is_deviant else STANDARD_FREQ,
            'onset_pp':       f"{tone_onset_pp:.6f}",
            'onset_vp':       _fmt_vp(tone_onset_vp),
            'isi_after':      f"{isi_after:.4f}" if isi_after else '',
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
    # 4. Response window (~1000 ms of fixation)  --  no trigger
    # -------------------------------------------------------------------
    # We use a flip-based loop rather than core.wait so that Windows'
    # message queue keeps getting pumped. Some PsychoPy keyboard
    # backends on Windows only notice key presses when win.flip() runs
    # -- if we sleep instead, key events during the response window are
    # silently dropped. Actively drain kb inside the loop to collect
    # presses as they arrive.
    #
    # Each frame we also record the VPIXX hardware clock time so that
    # any key events captured that frame can be tagged with an
    # approximate VP timestamp (within one frame of the true press).
    el_tracker.sendMessage('response_window_onset')
    trial_events = []
    resp_clock = core.Clock()
    while resp_clock.getTime() < RESPONSE_WINDOW:
        fixation.draw()
        trigger_patch.fillColor = trigger_color(TRIGGER_RESET)
        trigger_patch.draw()
        frame_pp = win.flip()
        dp.DPxUpdateRegCache()
        frame_vp = dp.DPxGetTime()
        events_this_frame, abort_key = get_keyboard_events(kb, KEY_CODES)
        if abort_key:
            return {'aborted': True}
        for ev in events_this_frame:
            # Approximate VP time = VP clock at this frame's flip, offset
            # by (event_pp - frame_pp) so PP-to-VP delta is preserved.
            ev['time_vp_est'] = frame_vp + (ev['time'] - frame_pp)
        trial_events.extend(events_this_frame)

    # Final drain to catch anything that arrived after the last flip.
    late_events, abort_key = get_keyboard_events(kb, KEY_CODES)
    if abort_key:
        return {'aborted': True}
    estimate_vp_times(late_events)
    trial_events.extend(late_events)

    # -------------------------------------------------------------------
    # 5. Classify this trial's response
    # -------------------------------------------------------------------

    # Log every event to the raw presses CSV
    for ev in trial_events:
        presses_log.append({
            'context':       'trial',
            'overall_trial': overall_trial,
            'block':         context_tag,
            'kind':          ev['kind'],
            'label':         ev['label'],
            'key_name':      ev['key_name'],
            'time_pp':       f"{ev['time']:.6f}",
            'time_vp_est':   _fmt_vp(ev['time_vp_est']),
        })
        all_presses_global.append((ev['label'], ev['time']))

    if abort_key:
        # Experimenter hit escape mid-trial. Bail out cleanly.
        return {'aborted': True}

    # Classify: find the first VALID press in the response window.
    # All times here are in the PsychoPy default clock.
    resp_min_pp = deviant_onset_pp + RESP_WIN_MIN
    resp_max_pp = deviant_onset_pp + RESP_WIN_MAX

    response_button   = None
    response_key_name = None
    response_time_pp  = None
    response_time_vp_est  = None
    rt_pp             = float('nan')
    rt_vp_est             = float('nan')
    outcome           = 'miss'

    for ev in trial_events:
        if ev['kind'] != 'press':
            continue
        if resp_min_pp <= ev['time'] <= resp_max_pp:
            response_button   = ev['label']
            response_key_name = ev['key_name']
            response_time_pp  = ev['time']
            response_time_vp_est  = ev['time_vp_est']
            rt_pp = response_time_pp - deviant_onset_pp
            # rt_vp_est uses the estimated response VP time; deviant_onset_vp
            # is a real VPIXX-captured value, but the response side is
            # keyboard-derived so the difference inherits ~one-frame
            # jitter from the response estimate.
            rt_vp_est = response_time_vp_est - deviant_onset_vp
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
    # 7. BLINK phase (500 ms text)
    # -------------------------------------------------------------------
    blink_text.draw()
    trigger_patch.fillColor = trigger_color(TRIGGER_BLINK)
    trigger_patch.draw()
    win.callOnFlip(el_tracker.sendMessage, 'blink_cue')
    blink_onset_pp = win.flip()
    dp.DPxUpdateRegCache()
    blink_onset_vp = dp.DPxGetTime()

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
        'aborted':              False,
        'overall_trial':        overall_trial,
        'block':                context_tag,
        'trial_in_block':       trial_in_block,
        'is_training':          is_training,
        'cue_hand':             cue_hand,
        'expected_button':      EXPECTED_BUTTONS[cue_hand],
        'n_standards':          n_std,
        'fixation_onset_pp':    f"{fixation_onset_pp:.6f}",
        'fixation_onset_vp':    _fmt_vp(fixation_onset_vp),
        'cue_onset_pp':         f"{cue_onset_pp:.6f}",
        'cue_onset_vp':         _fmt_vp(cue_onset_vp),
        'first_tone_onset_pp':  f"{first_tone_onset_pp:.6f}",
        'first_tone_onset_vp':  _fmt_vp(first_tone_onset_vp),
        'deviant_onset_pp':     f"{deviant_onset_pp:.6f}",
        'deviant_onset_vp':     _fmt_vp(deviant_onset_vp),
        'response_button':      response_button if response_button else '',
        'response_key_name':    response_key_name if response_key_name else '',
        'response_time_pp':     f"{response_time_pp:.6f}" if response_time_pp is not None else '',
        'response_time_vp_est': _fmt_vp(response_time_vp_est) if response_time_vp_est is not None else '',
        'rt_pp':                f"{rt_pp:.4f}" if not np.isnan(rt_pp) else '',
        'rt_vp_est':            _fmt_vp(rt_vp_est, precision=4) if not np.isnan(rt_vp_est) else '',
        'outcome':              outcome,
        'feedback_shown':       feedback_shown,
        'blink_onset_pp':       f"{blink_onset_pp:.6f}",
        'blink_onset_vp':       _fmt_vp(blink_onset_vp),
    }
    return result


# =============================================================================
# MAIN
# =============================================================================

# --- Participant info dialog ---
exp_info = {
    'participant':   '',
    'session':       '001',
    'dummy_eyelink': DUMMY_MODE,
    'dummy_vpixx':   DUMMY_VPIXX,
}
dlg = gui.DlgFromDict(
    dictionary=exp_info,
    title='Active Oddball (FT cued)',
    order=['participant', 'session', 'dummy_eyelink', 'dummy_vpixx'],
)
if not dlg.OK:
    core.quit()

# Read GUI values back into module-level flags. Helper functions and
# CSV writers reference these flags at call time, so overriding here
# takes effect throughout the run.
DUMMY_MODE  = bool(exp_info['dummy_eyelink'])
DUMMY_VPIXX = bool(exp_info['dummy_vpixx'])

# If pylink is not installed, force DUMMY_MODE on -- the script has no
# way to talk to a real EyeLink without it. Warn if the user disagrees.
if not _HAS_PYLINK:
    if not DUMMY_MODE:
        print("WARNING: pylink is not installed. Forcing DUMMY_MODE (EyeLink) on.")
        DUMMY_MODE = True

# Install pylink stand-ins when we don't have the real library. These
# only get called if DUMMY_MODE is on (the block above forces that
# when pylink is missing), so the mocks are covering EyeLink-disabled
# code paths only.
if not _HAS_PYLINK:
    class _MockPylink:
        """No-op stand-in for the pylink module.

        Provides the constants and utility functions the script uses,
        plus a mock EyeLink tracker whose methods are all no-ops (or
        return sensible defaults so isConnected/isRecording checks
        pass through the DUMMY_MODE code paths).
        """
        TRIAL_OK = 0
        ESC_KEY  = 27

        def __getattr__(self, name):
            # pumpDelay, msecDelay, openGraphicsEx, etc. -> no-ops
            return lambda *a, **k: None

        class EyeLink:
            def __init__(self, ip=None):
                self.ip = ip
            def __getattr__(self, name):
                if name == 'isConnected':
                    return lambda: 1
                if name == 'isRecording':
                    return lambda: 0        # 0 == TRIAL_OK
                if name == 'getTrackerVersionString':
                    return lambda: 'DUMMY EyeLink 0.0'
                return lambda *a, **k: None

    class _MockELGraphics:
        """Minimal stand-in for EyeLinkCoreGraphicsPsychoPy."""
        def __init__(self, tracker, win):
            self.tracker = tracker
            self.win     = win

    pylink = _MockPylink()
    EyeLinkCoreGraphicsPsychoPy = _MockELGraphics
    print("=== pylink not installed: using mock EyeLink module ===")

# If pypixxlib is not installed, force DUMMY_VPIXX on -- the script has
# no way to talk to a real DATAPixx3 without it. Warn if the user
# disagrees.
if not _HAS_PYPIXXLIB:
    if not DUMMY_VPIXX:
        print("WARNING: pypixxlib is not installed. Forcing DUMMY_VPIXX on.")
        DUMMY_VPIXX = True

# Set up the pypixxlib module (real or mock) based on DUMMY_VPIXX.
if DUMMY_VPIXX:
    print("=== DUMMY_VPIXX ENABLED ===")
    print("  Mock DATAPixx3: all dp.DPx* calls are no-ops.")
    print("  Audio: PsychoPy sound fallback (not vsync-locked).")
    print("  *_vp and *_vp_est CSV columns will be blank.")

    class _MockDPx:
        """No-op stand-in for pypixxlib._libdpx.

        Every DPx* call becomes a no-op. DPxGetTime returns 0.0 so
        that downstream arithmetic (e.g. time_vp_est calculations)
        doesn't crash; the resulting values are blanked in CSV output
        via _fmt_vp() rather than saved.
        """
        def __getattr__(self, name):
            if name == 'DPxGetTime':
                return lambda: 0.0
            return lambda *a, **k: None

    dp = _MockDPx()
else:
    dp = _real_dp

exp_info['date'] = data.getDateStr()

results_folder = 'results'
os.makedirs(results_folder, exist_ok=True)

sub = exp_info['participant'].replace('-', '').replace('_', '')
ses = exp_info['session'].replace('-', '').replace('_', '')
edf_fname = f"s{sub}s{ses}"[:8] + '.EDF'
local_edf_name = (f"sub-{exp_info['participant']}"
                  f"_ses-{exp_info['session']}_task-oddballftcued")

session_folder = os.path.join(results_folder, local_edf_name)
os.makedirs(session_folder, exist_ok=True)

filename_base = os.path.join(session_folder, local_edf_name)

# CSV file paths (rewritten cumulatively at each flush)
trials_csv_path  = filename_base + '_trials.csv'
tones_csv_path   = filename_base + '_tones.csv'
presses_csv_path = filename_base + '_presses.csv'


# --- VPIXX init ---
init_vpixx()


# --- KEY_CODES validation ---
# Fail fast if the researcher hasn't filled in the required entries.
_required_labels = set(EXPECTED_BUTTONS.values())
_present_labels  = set(KEY_CODES.values())
_missing = _required_labels - _present_labels
if _missing:
    print("=" * 60)
    print("ERROR: KEY_CODES is missing required finger labels:")
    for m in sorted(_missing):
        print(f"    {m}")
    print()
    print("This paradigm cues left/right index-finger responses and")
    print("cannot score responses without at least those two entries.")
    print("Fill in KEY_CODES at the top of this script with your")
    print("button box's key -> finger mapping and re-run.")
    print("=" * 60)
    close_vpixx()
    sys.exit(1)


# --- Keyboard for response input ---
# psychopy.hardware.keyboard.Keyboard uses the modern low-latency
# backend when available. getKeys() drains the internal buffer, so
# repeated calls only return NEW events.
kb = keyboard.Keyboard()
kb.clearEvents()   # discard any pre-experiment key presses


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

# Cue: two arrow TextStims flanking the fixation cross. The fixation
# cross is drawn separately as its own ShapeStim so it stays anchored
# at exact pixel (0, 0). Rendering the whole cue "<   +   <" as one
# TextStim would place the '+' glyph a pixel or two off center (font
# baseline / bounding-box metrics), causing the fixation to appear to
# shift during cue frames vs pure-fixation frames.
CUE_ARROW_OFFSET = 50   # pixels from center to each arrow's own center
cue_left = [
    visual.TextStim(win, text='<', color='white', height=60,
                     pos=(-CUE_ARROW_OFFSET, 0)),
    visual.TextStim(win, text='<', color='white', height=60,
                     pos=(+CUE_ARROW_OFFSET, 0)),
]
cue_right = [
    visual.TextStim(win, text='>', color='white', height=60,
                     pos=(-CUE_ARROW_OFFSET, 0)),
    visual.TextStim(win, text='>', color='white', height=60,
                     pos=(+CUE_ARROW_OFFSET, 0)),
]

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


# --- Build tones and load into VPIXX audio buffers ---
standard_wave = make_tone_int16(STANDARD_FREQ, TONE_DURATION,
                                AUDIO_SAMPLE_RATE, RAMP_DURATION)
deviant_wave  = make_tone_int16(DEVIANT_FREQ,  TONE_DURATION,
                                AUDIO_SAMPLE_RATE, RAMP_DURATION)

# Push both tones to DATAPixx3 RAM at their respective buffer addresses.
# In DUMMY_VPIXX mode this is a no-op via the mock dp module.
load_tone_into_buffer(standard_wave, STANDARD_BUFFER_ADDR)
load_tone_into_buffer(deviant_wave,  DEVIANT_BUFFER_ADDR)

# In dummy mode, also wrap the tones in PsychoPy Sound objects for
# audible playback via the computer speakers. Timing is not vsync-
# locked (typical PsychoPy audio latency 20-60 ms depending on backend);
# it's a functional demo, not a precise stimulus.
standard_stim = None
deviant_stim  = None
if DUMMY_VPIXX:
    from psychopy import sound
    standard_stim = sound.Sound(
        value=standard_wave.astype(np.float32) / 32767.0,
        sampleRate=AUDIO_SAMPLE_RATE, stereo=False,
    )
    deviant_stim = sound.Sound(
        value=deviant_wave.astype(np.float32) / 32767.0,
        sampleRate=AUDIO_SAMPLE_RATE, stereo=False,
    )

# Sample counts used by prep_tone_schedule() at trial time. Module-level
# names because prep_tone_schedule reads them from module scope.
standard_n_samples = int(len(standard_wave))
deviant_n_samples  = int(len(deviant_wave))
print(f"Standard tone: {standard_n_samples} samples @ {AUDIO_SAMPLE_RATE} Hz "
      f"({standard_n_samples / AUDIO_SAMPLE_RATE * 1000:.1f} ms)")
print(f"Deviant tone:  {deviant_n_samples} samples @ {AUDIO_SAMPLE_RATE} Hz "
      f"({deviant_n_samples / AUDIO_SAMPLE_RATE * 1000:.1f} ms)")


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

# Reset the keyboard buffer at experiment start so pre-instruction
# key presses do not leak into trial 1.
kb.clearEvents()

# Data containers -- flushed to CSV at every block boundary
trials_log         = []   # list of dicts, one per trial
tones_log          = []   # list of dicts, one per tone
presses_log        = []   # list of dicts, one per keyboard event
all_presses_global = []   # (label, time) tuples for in-memory scoring


# --- Instructions ---
instr = visual.TextStim(
    win,
    text=("You will hear a series of tones.\n\n"
          "On each trial an arrow cue appears:\n"
          "    <  <   = LEFT hand          >  >   = RIGHT hand\n\n"
          "After the cue you will hear several identical tones,\n"
          "followed by ONE different (higher) tone.\n\n"
          "As soon as you hear the DIFFERENT tone,\n"
          "press the INDEX FINGER button on the cued hand\n"
          "as quickly as possible.\n\n"
          "If you miss or press the wrong button, you'll see feedback.\n\n"
          "When 'BLINK' appears, you have half a second to blink.\n"
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
            el_tracker=el_tracker, kb=kb,
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
                el_tracker=el_tracker, kb=kb,
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

# One last drain of the keyboard buffer in case of trailing presses
_end_events, _ = get_keyboard_events(kb, KEY_CODES)
estimate_vp_times(_end_events)
for ev in _end_events:
    presses_log.append({
        'context':       'end',
        'overall_trial': overall_trial,
        'block':         'end',
        'kind':          ev['kind'],
        'label':         ev['label'],
        'key_name':      ev['key_name'],
        'time_pp':       f"{ev['time']:.6f}",
        'time_vp_est':   _fmt_vp(ev['time_vp_est']),
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


# --- Overall summary ---
main_trials = [t for t in trials_log if not t['is_training']]
n_main      = len(main_trials)
n_correct   = sum(1 for t in main_trials if t['outcome'] == 'correct')
n_wrong     = sum(1 for t in main_trials if t['outcome'] == 'wrong_button')
n_miss      = sum(1 for t in main_trials if t['outcome'] == 'miss')

pct_correct = 100.0 * n_correct / n_main if n_main > 0 else 0.0
correct_rts = [float(t['rt_pp']) for t in main_trials
               if t['outcome'] == 'correct' and t['rt_pp'] != '']
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
