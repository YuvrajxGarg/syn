# SYN brand

- `mark.svg` (white letters), `mark-dark.svg` (for light backgrounds), `mark-currentcolor.svg`: the outlined "syn" wordmark with the lime sync link. The link runs exactly from the baseline to the x-height. Regenerate with `python make_mark.py` (needs fonttools and Inter Display Black).
- `icon.png`, `icon.ico`, `AppIcon.icns`: the app icon, made by `assets/make_icon.py`.
- `tokens.css`: colours, radii and fonts shared with the app.
- `splash.css`: the logo animation. One continuous motion (letters rise in, the dots slide in, the line draws, one pulse) with no hold in the middle. Animated letters are padded `.1em .2em .3em` with matching negative margins so nothing clips at the edges.
