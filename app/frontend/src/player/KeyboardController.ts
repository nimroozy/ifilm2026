import { useEffect } from 'react';

export interface KeyboardHandlers {
  togglePlay: () => void;
  seekBy: (delta: number) => void;
  volumeBy: (delta: number) => void;
  toggleMute: () => void;
  toggleFullscreen: () => void;
  togglePiP?: () => void;
  toggleCaptions?: () => void;
  escape?: () => void;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable;
}

export function useKeyboardController(enabled: boolean, handlers: KeyboardHandlers) {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      const key = event.key;
      if (key === ' ' || key === 'k' || key === 'K') {
        event.preventDefault();
        handlers.togglePlay();
      } else if (key === 'j' || key === 'J') {
        event.preventDefault();
        handlers.seekBy(-10);
      } else if (key === 'l' || key === 'L') {
        event.preventDefault();
        handlers.seekBy(10);
      } else if (key === 'ArrowLeft') {
        event.preventDefault();
        handlers.seekBy(-10);
      } else if (key === 'ArrowRight') {
        event.preventDefault();
        handlers.seekBy(10);
      } else if (key === 'ArrowUp') {
        event.preventDefault();
        handlers.volumeBy(0.05);
      } else if (key === 'ArrowDown') {
        event.preventDefault();
        handlers.volumeBy(-0.05);
      } else if (key === 'm' || key === 'M') {
        event.preventDefault();
        handlers.toggleMute();
      } else if (key === 'f' || key === 'F') {
        event.preventDefault();
        handlers.toggleFullscreen();
      } else if ((key === 'p' || key === 'P') && handlers.togglePiP) {
        event.preventDefault();
        handlers.togglePiP();
      } else if ((key === 'c' || key === 'C') && handlers.toggleCaptions) {
        event.preventDefault();
        handlers.toggleCaptions();
      } else if (key === 'Escape' && handlers.escape) {
        handlers.escape();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [enabled, handlers]);
}
