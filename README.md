# OPM-MEG Active Oddball

PsychoPy scripts for auditory oddball paradigms in the Princeton
Neuroscience Institute OPM-MEG facility. Based on the FieldTrip cued
oddball paradigm (bimanual left/right index-finger responses,
3 blocks × 100 trials, continuous EyeLink recording, VPIXX pixel-mode
triggers).

## Paradigm variants

- `oddball_active_v2_ft_cued.py` — VPIXX audio + VPIXX ResponsePixx
- `oddball_active_v2_ft_cued_psychopy_audio.py` — PsychoPy audio + VPIXX ResponsePixx
- `oddball_active_v2_ft_cued_pyaud_kbd.py` — PsychoPy audio + keyboard (Current Designs)

## Reference / utility scripts

- `buttonpresses.py` — reference for VPIXX ResponsePixx button reading
- `pixel_mode_b_reference.py` — reference for VPIXX Pixel Mode B triggers
- `vpixx_button_test.py` — diagnostic to verify button-box DIN mapping

## Requirements

- PsychoPy 2026.1+
- pypixxlib (VPIXX)
- pylink (SR Research EyeLink)
- numpy

## Data handling

The `results/` folder is gitignored. Participant data must never be
committed to this repository.
