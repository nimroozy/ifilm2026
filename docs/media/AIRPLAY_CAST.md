# AirPlay and Google Cast status

## AirPlay

- Control is shown **only** when WebKit `HTMLMediaElement.webkitShowPlaybackTargetPicker` or the Remote Playback API `remote.prompt()` is available on the video element.
- Chromium desktop typically does **not** support AirPlay; the control stays hidden there (no fake support).
- Protected HLS sessions continue to use opaque playback tokens; AirPlay uses the same in-page media element session when the browser/OS routes it.
- **Verification:** Not claimed verified on real Safari/iPhone/Apple TV in this milestone unless hardware testing is recorded separately.

## Google Cast

- Cast remains **disabled** in the player UI (`cast-button-disabled`).
- A secure Cast integration requires a custom receiver compatible with protected session playback (no permanent package URLs, no long-lived raw tokens).
- Deferred until that receiver infrastructure exists.

## Picture in Picture

- Gated on `document.pictureInPictureEnabled`.
- Keyboard: `P` toggles PiP when supported.
