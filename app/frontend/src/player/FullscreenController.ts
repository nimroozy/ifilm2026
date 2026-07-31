export async function requestFullscreen(el: HTMLElement): Promise<void> {
  const anyEl = el as HTMLElement & {
    webkitRequestFullscreen?: () => void;
    msRequestFullscreen?: () => void;
  };
  if (el.requestFullscreen) await el.requestFullscreen();
  else if (anyEl.webkitRequestFullscreen) anyEl.webkitRequestFullscreen();
  else if (anyEl.msRequestFullscreen) anyEl.msRequestFullscreen();
}

export async function exitFullscreen(): Promise<void> {
  const doc = document as Document & {
    webkitExitFullscreen?: () => void;
    msExitFullscreen?: () => void;
  };
  if (document.fullscreenElement) await document.exitFullscreen();
  else if (doc.webkitExitFullscreen) doc.webkitExitFullscreen();
  else if (doc.msExitFullscreen) doc.msExitFullscreen();
}

export function isFullscreen(): boolean {
  const doc = document as Document & { webkitFullscreenElement?: Element };
  return Boolean(document.fullscreenElement || doc.webkitFullscreenElement);
}

export function canPictureInPicture(video?: HTMLVideoElement | null): boolean {
  if (!video) {
    return typeof document !== 'undefined' && 'pictureInPictureEnabled' in document
      ? Boolean((document as Document & { pictureInPictureEnabled?: boolean }).pictureInPictureEnabled)
      : false;
  }
  const anyVideo = video as HTMLVideoElement & {
    requestPictureInPicture?: () => Promise<PictureInPictureWindow>;
    disablePictureInPicture?: boolean;
  };
  return Boolean(anyVideo.requestPictureInPicture) && !anyVideo.disablePictureInPicture;
}

export async function togglePictureInPicture(video: HTMLVideoElement): Promise<boolean> {
  const doc = document as Document & {
    pictureInPictureElement?: Element;
    exitPictureInPicture?: () => Promise<void>;
  };
  const anyVideo = video as HTMLVideoElement & {
    requestPictureInPicture?: () => Promise<PictureInPictureWindow>;
    disablePictureInPicture?: boolean;
  };
  if (!anyVideo.requestPictureInPicture || anyVideo.disablePictureInPicture) return false;
  if (doc.pictureInPictureElement) {
    await doc.exitPictureInPicture?.();
    return false;
  }
  await anyVideo.requestPictureInPicture();
  return true;
}
