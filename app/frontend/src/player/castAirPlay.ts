/** WebKit AirPlay / remote playback helpers. Never fake support. */

export function isAirPlaySupported(video?: HTMLVideoElement | null): boolean {
  if (typeof window === 'undefined') return false;
  const candidate = video as (HTMLVideoElement & {
    webkitShowPlaybackTargetPicker?: () => void;
  }) | null;
  if (candidate && typeof candidate.webkitShowPlaybackTargetPicker === 'function') {
    return true;
  }
  // Remote Playback API (partial Chromium / future)
  const remote = candidate?.remote as { prompt?: () => Promise<void> } | undefined;
  return typeof remote?.prompt === 'function';
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
  const remote = video.remote as { prompt?: () => Promise<void> } | undefined;
  if (typeof remote?.prompt === 'function') {
    void remote.prompt();
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
