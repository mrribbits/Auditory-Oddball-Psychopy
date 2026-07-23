"""Diagnostic: prints every key press seen by PsychoPy.

Uses the same psychopy.hardware.keyboard.Keyboard the paradigm uses,
plus a fullscreen window so we can also detect the classic
'window-doesn't-have-focus' failure mode on Windows.

Press keys on your button box. Each press should print a line.
Press ESC to quit.
"""

from psychopy import visual, core
from psychopy.hardware import keyboard

win = visual.Window(fullscr=True, color='black', screen=0, units='pix')
msg = visual.TextStim(
    win,
    text=("Press buttons on your box.\n"
          "The console should print each key name.\n\n"
          "Press ESC to quit."),
    color='white', height=28, wrapWidth=1000,
)

kb = keyboard.Keyboard()
kb.clearEvents()

msg.draw()
win.flip()

print("Listening for keys... Press ESC to quit.")
clock = core.Clock()

while True:
    keys = kb.getKeys(waitRelease=False)   # NO keyList filter -- see ALL keys
    for k in keys:
        print(f"    key.name={k.name!r}  key.tDown={k.tDown:.4f}")
        if k.name == 'escape':
            win.close()
            core.quit()
    core.wait(0.01)
