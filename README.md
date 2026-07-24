# OPM-MEG Active Oddball

PsychoPy script for active auditory oddball paradigm in the Scully OPM-MEG facility. 
Based on the FieldTrip cued oddball paradigm:
https://www.fieldtriptoolbox.org/workshop/natmeg2014/meg_audodd/
Includes bimanual left/right index-finger responses, 3 blocks × 100 trials, 
continuous EyeLink recording, VPIXX pixel-mode triggers, VPIXX audio delivery.

- `oddball_active_cued_ft_VPIXXaudio_KBDinput.py` — VPIXX audio + keyboard input

## Software Requirements

- PsychoPy 2026.1+
- pypixxlib (VPIXX)
- pylink (SR Research EyeLink)

## Hardware Requirements
- VPixx DATAPixx3, SOUNDPixx, PROPixx
- SR Eyelink

## Data handling

The `results/` folder is gitignored.
