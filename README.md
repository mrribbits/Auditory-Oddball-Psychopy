# OPM-MEG Active Oddball

PsychoPy script for an active auditory oddball paradigm in the Scully OPM-MEG facility. Based on the [FieldTrip cued oddball paradigm](https://www.fieldtriptoolbox.org/workshop/natmeg2014/meg_audodd/).

Bimanual left/right index-finger responses, 3 blocks × 100 trials (~51 minutes), continuous EyeLink recording, VPIXX pixel-mode triggers, and hardware-scheduled VPIXX audio.

## Trial structure

```
+-----------+-----+-----------------+---------+----------+-------+
| fixation  | cue | auditory stim   | resp.   | feedback | BLINK |
|  1500 ms  |500ms|  4000-8800 ms   | 1000 ms |  400 ms  | 500 ms|
|     +     | >+> | tones + oddball |    +    |  (errors |       |
|           | or  |                 |         |   only)  |       |
|           | <+< |                 |         |          |       |
+-----------+-----+-----------------+---------+----------+-------+
```

The subject sees an arrow cue directing them to prepare a left- or right-hand response, hears 3–7 standard tones (1000 Hz) followed by one deviant tone (1200 Hz), and presses the index-finger button on the cued hand as quickly as possible.

## Files

- `oddball_active_cued_ft_VPIXXaudio_KBDinput.py` — main script
- `EyeLinkCoreGraphicsPsychoPy.py` — renders EyeLink calibration graphics inside PsychoPy
- `*.wav` — sound files used by EyeLink for calibration / target beeps

## Requirements

**Software:**
- PsychoPy 2026.1+
- pypixxlib (VPIXX)
- pylink (SR Research)
- You must obtain EyeLinkCoreGraphicsPsychoPy.py from SR Research's EyeLink Developers Kit.

For Windows setup, an installer script that installs PsychoPy and the required dependencies is available at [ScullyCenter-Psychopy-Install-Win](https://github.com/mrribbits/ScullyCenter-Psychopy-Install-Win).

**Hardware:**
- VPixx DATAPixx3 + SOUNDPixx + PROPixx
- SR Research EyeLink
- HID-keyboard button box (e.g. Current Designs)

## Running the script

Most common way: open the `.py` file in the **PsychoPy Coder** window and click Run.

Alternative for users with PsychoPy installed in a conda environment:

```bash
python oddball_active_cued_ft_VPIXXaudio_KBDinput.py
```

Either way, a startup dialog asks for participant ID, session number, and two dummy-mode checkboxes:

- **`dummy_eyelink`** — run without EyeLink Host PC. Auto-forced on if `pylink` isn't installed.
- **`dummy_vpixx`** — run without a DATAPixx3. Audio falls back to PsychoPy sound (audible but not vsync-locked), and `*_vp` / `*_vp_est` columns in the output CSVs are left blank. Auto-forced on if `pypixxlib` isn't installed.

A clean laptop with only PsychoPy installed can still run the paradigm end-to-end for demo or development purposes.

## Pre-flight checklist

1. VPIXX device on and reachable (`DPxOpen` succeeds), or check `dummy_vpixx`
2. VPIXX running Pixel Mode B (the script enables it)
3. Audio wired to the desired path (headphones or loudspeakers) at audible volume
4. Button box emitting keyboard events; update `KEY_CODES` in the script to match your box
5. Button box TTL trigger output wired into the MEG trigger channel
6. EyeLink Host PC at 100.1.1.1, or check `dummy_eyelink`
7. Audio transit delay measured (microphone at earpiece); record for latency correction in analysis

## Output files

Written to `results/sub-<p>_ses-<s>_task-oddballftcued/`:

- `..._trials.csv` — one row per trial (main behavioral log)
- `..._tones.csv` — one row per tone with per-tone VPIXX timestamps
- `..._presses.csv` — one row per keyboard event (all presses, not just scored responses)
- `....EDF` — EyeLink data downloaded from the Host PC at session end

CSVs are flushed at the end of every block, so a crash mid-run doesn't lose completed blocks.

Timestamp columns are suffixed by clock provenance:

- **`_pp`** — PsychoPy default clock (behavioral RT reference)
- **`_vp`** — VPIXX DATAPixx3 hardware clock (MEG alignment reference)
- **`_vp_est`** — Estimated VPIXX-clock time for events VPIXX didn't directly detect (keyboard presses). Accurate to within ~one video frame; use the button box's TTL wiring into the MEG trigger channel as the definitive response reference.

## Technical details

The module docstring at the top of `oddball_active_cued_ft_VPIXXaudio_KBDinput.py` covers everything not in this README: audio scheduling and vsync locking, trigger scheme, trigger vs. perceived-stimulus timing corrections, keyboard input caveats, response scoring rules, and block structure. Read there for extending or debugging the script.
