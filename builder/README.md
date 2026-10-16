# OPM-MEG Active Oddball — Builder version

PsychoPy **Builder** implementation of the FieldTrip cued auditory oddball paradigm for the Scully OPM-MEG facility. Functionally identical to the [Coder version](../oddball_active_cued_ft_VPIXXaudio_KBDinput.py); this version is set up for users who prefer the Builder GUI.

Based on the [FieldTrip cued oddball paradigm](https://www.fieldtriptoolbox.org/workshop/natmeg2014/meg_audodd/).

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

- `oddball_cued_builder.psyexp` — the Builder file (open in PsychoPy via File → Open)
- `images/fixTarget.bmp` — EyeLink drift/calibration target
- `qbeep.wav`, `type.wav`, `error.wav` — EyeLink calibration beeps

## Requirements

**Software:**
- PsychoPy 2026.1+ (built and tested with 2026.2.4)
- `psychopy-eyelink` plugin v2.2.1.1+
- `pypixxlib` (VPIXX)
- `pylink` (SR Research)

For Windows setup, see [ScullyCenter-Psychopy-Install-Win](https://github.com/mrribbits/ScullyCenter-Psychopy-Install-Win).

**Hardware:**
- VPixx DATAPixx3 + SOUNDPixx + PROPixx
- SR Research EyeLink
- HID-keyboard button box (e.g. Current Designs)

## Opening and running

1. **Launch PsychoPy first**, then open the `.psyexp` with **File → Open**. If you double-click the `.psyexp`, the EyeLink plugin components can load as "puzzle pieces" with their settings missing.
2. Keep `images/` and the `.wav` files in the same folder as the `.psyexp`.
3. Use **Run** (green arrow), not **Pilot**. The DATAPixx3's Pixel Mode requires a full-screen window; Pilot mode uses an 800×600 window and the experiment will refuse to start unless you also enable VPIXX dummy mode.

The startup dialog asks for:

- `participant` — subject ID
- `session` — session number (default `01`)
- `Use dummy VPIXX?` — dropdown with `no` / `yes` (default `no`)

Pick `yes` to run without a DATAPixx3 (audio falls back to PsychoPy sound; `_vp` columns in the data are left blank). If `pypixxlib` isn't installed at all, dummy VPIXX mode is auto-forced on with a warning printed to the Runner.

The EyeLink dummy mode is a separate checkbox on the `Initialize` component inside the `eyelinkSetup` routine (not in the startup dialog).

## Flow

```
eyelinkSetup             experimenter screen -> Initialize -> Camera Setup (HV13)
instruct                 task instructions; also runs vpixxSetup / triggerSetup /
                         toneSetup / sequenceGen (fresh conditions CSVs for this run)
eyelinkDriftCheck        initial drift check
triggersOn               enables Pixel Mode B

training_trials  (20 trials, from a session-generated conditions CSV)
  trialSetup             parses this trial's row, sets tone_loop_training nReps
  fixation (1500 ms)
  cue (500 ms)           arrows + cue trigger
  tone_loop_training (nReps = n_standards + 1)
    tone                 single tone with trigger + ISI
  response_window (1000 ms)   flip-based HID polling
  feedback (400 ms)      skipped on correct
  blink (500 ms)
  trialLog               writes trial / tones / presses rows to TSVs

trainingTransition       "Training complete, press SPACE for main experiment"
eyelinkDriftCheck_post_training

block_loop (3 blocks)
  block_trials (100 trials each, from this block's generated CSV)
    [same inner routines as training, with tone_loop_main instead of
     tone_loop_training; both use the same `tone` routine]
  breakScreen            15-s rest countdown + experimenter SPACE
                         (skipped after block 3)
  eyelinkDriftCheck_between_blocks
                         (skipped after block 3)

thanks                   Pixel Mode off + TASK_END; 3-s end screen
```

**Why two tone loops** (`tone_loop_training` and `tone_loop_main`): Builder's Flow panel keys its loop registry by name, so each loop in the Flow needs a unique name. The `tone` routine is reused by both — the trial code picks whichever loop is active via `is_training_bool`.

## Trigger scheme (VPIXX Pixel Mode B, blue channel)

| Name | RGB | MEG trigger | Event |
|---|---|---|---|
| `TRIG_STANDARD` | (0, 0, 1) | 1 | standard tone onset |
| `TRIG_DEVIANT` | (0, 0, 2) | 2 | deviant tone onset |
| `TRIG_BLINK` | (0, 0, 4) | 4 | BLINK cue onset |
| `TRIG_CUE_LEFT` | (0, 0, 8) | 8 | left-hand cue onset |
| `TRIG_CUE_RIGHT` | (0, 0, 16) | 16 | right-hand cue onset |
| `TRIG_FEEDBACK` | (0, 0, 32) | 32 | MISS or WRONG BUTTON onset |

Unused values on the 8-line channel: 64, 128. Each trigger is one video frame long (~8.3 ms at 120 Hz).

Response events are **not** pixel-triggered. Wire the button box's TTL output directly to the MEG trigger channel for sample-precise response timing; the keyboard timestamps logged here go through the OS HID pipeline and carry a few ms of jitter.

## Code components

Every code component starts with a header comment block (same style as the Scully Builder samples): when it runs, what it does, and where each name comes from.

| Component | Routine | Tab(s) | Job |
|---|---|---|---|
| `vpixxSetup` | instruct | Before / Begin Exp | load pypixxlib, dummy-mode fallback, open DATAPixx3 (Pixel Mode off), atexit cleanup |
| `triggerSetup` | instruct | Before / Begin Exp | trigger colours; the trigger pixel; `setTriggerPixel`, `sendTrigger`, `recordVpixxTime` |
| `toneSetup` | instruct | Before / Begin Exp | make the 1000 Hz standard and 1200 Hz deviant tones; copy both to the DATAPixx3; dummy-mode sounds |
| `sequenceGen` | instruct | Before Exp / Begin Routine | module imports + generate fresh conditions CSVs for training + 3 main blocks |
| `trialTimingSetup` | instruct | Before Exp | timing constants (FIXATION_DURATION, CUE_DURATION, etc.) |
| `responseClassifySetup` | instruct | Before / Begin Exp | import `keyboard`, create the `kb` object and `KEY_CODES` mapping |
| `cueSetup` | instruct | Begin Exp | create the cue-arrow TextStims (left-pair / right-pair) |
| `breakSetup` | instruct | Begin Exp | `INTERBLOCK_MIN_REST` constant |
| `logFilesSetup` | instruct | Before / Begin Exp | open the three TSV log files; register close-at-exit |
| `taskStartMsg` | instruct | End Routine | write TASK_START into the EDF |
| `pixelModeOn` | triggersOn | Begin Routine | enable Pixel Mode B |
| `trialSetupCode` | trialSetup | Begin Routine | parse this trial's row, set `tone_loop_reps`, clear per-trial state |
| `blockControl` | trialSetup | Begin Routine | set `block_label` and `trial_in_block` |
| `cuePresent` | cue | Begin / Each Frame / End | send cue trigger, draw arrow pair, record cue onset |
| `tonePresent` | tone | Begin / Each Frame / End | arm the audio schedule and tone trigger, record onset, log per-tone row |
| `responseClassify` | response_window | Begin / Each Frame / End | flip-based `kb.getKeys`, classify first in-window press, log presses |
| `feedbackSelect` | feedback | Begin / Each Frame | pick MISS vs WRONG BUTTON text, send FEEDBACK trigger (TextComponent draws) |
| `blinkPresent` | blink | Begin / Each Frame / End | send BLINK trigger, record onset (TextComponent draws) |
| `trialLogWrite` | trialLog | End Routine | write one trial row (+ per-trial tone and press rows) |
| `trainingTransitionText` | trainingTransition | Begin Routine | compute training accuracy, build transition message |
| `breakControl` | breakScreen | Begin / Each Frame | 15-s countdown + SPACE wait, `kb`-based polling |
| `pixelModeOff` | thanks | Begin Routine | disable Pixel Mode B |
| `taskEndMsg` | thanks | Begin Routine | write TASK_END into the EDF |

**Rendering note:** the feedback text (MISS / WRONG BUTTON) and the BLINK text are drawn by TextComponents in their respective routines, not by code. The code picks the string/size; Builder handles the drawing lifecycle. This is more reliable than drawing imperatively from Each Frame code.

## Data output

Written to `results/<participant>_oddball_cued_builder_<date>/`:

- `<...>_trials_log.tsv` — one row per trial (main behavioural log)
- `<...>_tones_log.tsv` — one row per tone with per-tone VPIXX timestamps
- `<...>_presses_log.tsv` — one row per detected keyboard event
- `<...>_training.csv` / `<...>_block1.csv` / `_block2.csv` / `_block3.csv` — the exact conditions sequences this session used (regenerated each run; keep for provenance)
- `<...>.EDF` — EyeLink data from the Host PC
- Standard PsychoPy wide CSV (one row per trial, Builder-written)

TSV files are flushed after every trial (crash-safe: if the experiment dies during block 2, block 1 data is on disk).

**Timestamp columns** are suffixed by clock provenance:

- `_pp` — PsychoPy default clock (behavioural RT reference)
- `_vp` — VPIXX DATAPixx3 hardware clock (MEG alignment reference)
- `_vp_est` — Estimated VPIXX-clock time for events VPIXX didn't directly detect (keyboard presses). Accurate to within ~one video frame; use the button box's TTL wiring into the MEG trigger channel as the definitive response reference.

In dummy VPIXX mode, all `_vp` and `_vp_est` columns are left blank so the file visibly says "this was a dummy run."

## Pre-flight checklist

1. VPIXX device on and reachable, or pick `yes` for `Use dummy VPIXX?` in the start dialog
2. VPIXX in Pixel Mode B (the experiment enables it after the drift check)
3. Audio wired to the desired path (headphones or loudspeakers) at audible volume
4. Button box emits `7` for left index finger and `2` for right index finger (Scully convention). If it uses different key names, edit `KEY_CODES` in the `responseClassifySetup` code component (instruct routine, Begin Experiment tab)
5. Button box TTL trigger output wired into the MEG trigger channel
6. EyeLink Host PC at 100.1.1.1, or tick Dummy Mode on the `Initialize` component in `eyelinkSetup`
7. Audio transit delay measured (microphone at earpiece); record for latency correction in analysis

## Builder-GUI tweaks you may need

Builder settings in **Experiment Settings** (gear icon) that may need to be changed for your rig:

- **Monitor** — currently set to `MBA 15-inch` for local testing. Change to your lab-calibrated monitor profile (e.g. `testMonitor`) before taking this to the MEG stim PC.
- **Screen** — `1` (whichever display the subject sees)
- **Window size** — `[1920, 1080]` (the Scully MEG display)
- **Frame rate** — `120` (DATAPixx3 projector)

## Dummy modes (independent)

- **EyeLink dummy** — tick Dummy Mode on the `Initialize` component in `eyelinkSetup`. Also auto-forced on if `pylink` isn't installed.
- **VPIXX dummy** — pick `yes` for `Use dummy VPIXX?` in the start dialog. Also auto-forced on if `pypixxlib` isn't installed. Tones play through PsychoPy sound (imprecise timing), no MEG triggers, `_vp` / `_vp_est` columns stay blank in the data.

A clean laptop with only PsychoPy installed (no `pylink`, no `pypixxlib`) can still run the paradigm end-to-end for demo or development.

## Quitting

- **ESC** aborts the experiment (quits during a trial or at the break screen). The EyeLink plugin uses ESC for its own calibration flow, so pressing ESC during the Camera Setup screen enters the EyeLink setup mode rather than quitting the experiment — ESC's "quit the experiment" behavior only applies during our own routines.
- **Ctrl-C** in the Runner window always aborts; the EDF is still retrieved (if real EyeLink) and the DATAPixx3 is released via `atexit` (if real VPIXX).

## Technical details

The code components use the same timing-critical patterns as the Coder version:

- `DPxWriteRegCacheAfterVideoSync` arms the tone-schedule start command to fire at the next vsync (same vsync that puts the trigger pixel on DOUT) — audio onset is aligned with the MEG trigger edge in hardware.
- Between `prep_tone_schedule` and the `DPxStartAudSched` + `DPxWriteRegCacheAfterVideoSync` pair, no other code may call `DPxUpdateRegCache` or `DPxWriteRegCache` (would clobber the pending arm). `recordVpixxTime` is deferred to after the flip via `win.callOnFlip`.
- The response window uses a flip-based poll loop (`kb.getKeys` on each frame) rather than `core.wait`, because the OS message queue needs to be pumped for keyboard events to be noticed on Windows.
- `response_window`'s Begin Routine drains any key events pressed BEFORE the window opens (e.g., a correct press during the deviant tone itself). The scoring window spans 150–1400 ms after deviant onset, which includes the last 250 ms of the deviant tone — a fast press there should count.

See the module docstring in [`oddball_active_cued_ft_VPIXXaudio_KBDinput.py`](../oddball_active_cued_ft_VPIXXaudio_KBDinput.py) for the full timing rationale, trigger-vs-perceived-stimulus corrections, and response-scoring details.
