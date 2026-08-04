/** WebKit AirPlay helpers. Never fake support or conflate with Chromium Remote Playback / Cast. */

export function isAirPlaySupported(video?: HTMLVideoElement | null): boolean {
  if (typeof window === 'undefined') return false;
  const candidate = video as (HTMLVideoElement & {
    webkitShowPlaybackTargetPicker?: () => void;
  }) | null;
  // AirPlay UI is WebKit-only. Chromium `video.remote.prompt` is Remote Playback, not AirPlay.
  return typeof candidate?.webkitShowPlaybackTargetPicker === 'function';
}

export function showAirPlayPicker(video: HTMLVideoElement | null | undefined): boolean {
  if (!video) return false;
  const webkit = video as HTMLVideoElement & {
    webkitShowPlaybackTargetPicker?: () => void;
  };
  if (typeof webkit.webkitShowPlaybackTargetPicker === 'function') {
    webkit.webkitShowPlaybackTargetPicker();
    return true;
  }
  return false;
}

export function isPiPSupported(): boolean {
  if (typeof document === 'undefined') return false;
  return (
    'pictureInPictureEnabled' in document &&
    Boolean((document as Document & { pictureInPictureEnabled?: boolean }).pictureInPictureEnabled)
  );
}
