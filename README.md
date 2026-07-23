# OPM-MEG Active Oddball

PsychoPy scripts for auditory oddball paradigms in the Scully OPM-MEG facility. 
Based on the FieldTrip cued oddball paradigm (bimanual left/right index-finger responses,
3 blocks × 100 trials, continuous EyeLink recording, VPIXX pixel-mode triggers).

## Paradigm variants

- `oddball_active_v2_ft_cued.py` — VPIXX audio + VPIXX ResponsePixx
- `oddball_active_v2_ft_cued_psychopy_audio.py` — PsychoPy audio + VPIXX ResponsePixx
- `oddball_active_v2_ft_cued_pyaud_kbd.py` — PsychoPy audio + keyboard (Current Designs)
- `oddball_active_v2_ft_cued_VPIXXaudio_KBDinput.py` — VPIXX audio + keyboard (Current Designs)

## Requirements

- PsychoPy 2026.1+
- pypixxlib (VPIXX)
- pylink (SR Research EyeLink)
- numpy

## Data handling

The `results/` folder is gitignored.
