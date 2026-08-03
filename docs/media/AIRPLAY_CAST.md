# AirPlay and Google Cast status

## AirPlay

- Control is shown **only** when WebKit `HTMLMediaElement.webkitShowPlaybackTargetPicker` is available on the video element.
- Chromium `HTMLMediaElement.remote.prompt` (Remote Playback API) is **not** treated as AirPlay and must not show the AirPlay control.
- The player sets `x-webkit-airplay="allow"` so WebKit can route custom-control playback to AirPlay receivers.
- Chromium desktop typically does **not** support AirPlay; the control stays hidden there (no fake support).
- Protected HLS sessions continue to use opaque playback tokens; AirPlay uses the same in-page media element session when the browser/OS routes it.
- **Verification status: Implemented, hardware verification pending** (no claim of real AirPlay playback success without Safari/Apple hardware).

## Google Cast

- Cast remains **disabled** in the player UI (`cast-button-disabled`).
- A secure Cast integration requires a custom receiver compatible with protected session playback (no permanent package URLs, no long-lived raw tokens).
- Deferred until that receiver infrastructure exists.

## Picture in Picture

- Gated on `document.pictureInPictureEnabled`.
- Keyboard: `P` toggles PiP when supported.
