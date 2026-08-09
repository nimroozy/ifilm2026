import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PlayerControls } from '../PlayerControls';
import { localizeAudioTrackName, localizeSubtitleTrackName } from '../trackLabels';
import { translations } from '@/data/translations';

describe('PlayerControls AirPlay / LTR', () => {
  const baseProps = {
    visible: true,
    playing: false,
    muted: false,
    volume: 1,
    currentTime: 10,
    duration: 100,
    buffered: 40,
    levels: [{ index: 0, height: 240, label: '240p', bitrate: 1 }],
    currentLevel: -1,
    manualQualitySupported: true,
    audioTracks: [
      { id: 0, name: 'English', lang: 'en' },
      { id: 1, name: 'Persian Dub', lang: 'fa' },
    ],
    audioTrackId: 0,
    subtitleTracks: [
      { id: 0, name: 'English', lang: 'en' },
      { id: 1, name: 'Pashto', lang: 'ps' },
    ],
    subtitleTrackId: -1,
    playbackRate: 1,
    isFs: false,
    onTogglePlay: () => undefined,
    onSeek: () => undefined,
    onVolume: () => undefined,
    onToggleMute: () => undefined,
    onQuality: () => undefined,
    onAudio: () => undefined,
    onSubtitle: () => undefined,
    onRate: () => undefined,
    onFullscreen: () => undefined,
    onPiP: () => undefined,
  };

  it('renders AirPlay icon and never shows AP text when supported', () => {
    render(
      <PlayerControls
        {...baseProps}
        airPlaySupported
        onAirPlay={vi.fn()}
        labels={{ audio: 'Audio', subtitles: 'Subtitles', off: 'Off' }}
      />
    );
    const button = screen.getByTestId('airplay-button');
    expect(button).toBeTruthy();
    expect(button.textContent).not.toMatch(/\bAP\b/);
    expect(button.querySelector('svg')).toBeTruthy();
  });

  it('hides AirPlay when unsupported', () => {
    render(<PlayerControls {...baseProps} airPlaySupported={false} onAirPlay={vi.fn()} />);
    expect(screen.queryByTestId('airplay-button')).toBeNull();
  });

  it('forces LTR on controls root', () => {
    render(<PlayerControls {...baseProps} />);
    const controls = screen.getByTestId('player-controls');
    expect(controls.getAttribute('dir')).toBe('ltr');
    expect(controls.style.direction).toBe('ltr');
  });

  it('exposes audio and subtitle selectors', () => {
    render(
      <PlayerControls
        {...baseProps}
        labels={{ audio: 'Audio', subtitles: 'Subtitles', off: 'Off' }}
      />
    );
    expect(screen.getByTestId('audio-selector')).toBeTruthy();
    expect(screen.getByTestId('subtitle-selector')).toBeTruthy();
  });
});

describe('track label i18n', () => {
  it('localizes dubbed audio without storing UI text in DB shape', () => {
    expect(localizeAudioTrackName('fa', translations.en.player, { isDubbed: true })).toBe(
      'Persian Dub'
    );
    expect(localizeAudioTrackName('fa', translations.fa.player, { isDubbed: true })).toBe(
      'دوبله فارسی'
    );
    expect(localizeAudioTrackName('ps', translations.ps.player, { isDubbed: true })).toBe(
      'پښتو ژباړه'
    );
  });

  it('localizes subtitle languages', () => {
    expect(localizeSubtitleTrackName('en', translations.en.player)).toBe('English');
    expect(localizeSubtitleTrackName('fa', translations.fa.player)).toBe('فارسی');
    expect(localizeSubtitleTrackName('ps', translations.ps.player)).toBe('پښتو');
  });
});

describe('dubbed localization keys', () => {
  it('uses corrected dubbed copy across locales', () => {
    expect(translations.en.movie.dubbed).toBe('Dubbed');
    expect(translations.fa.movie.dubbed).toBe('دوبله شده');
    expect(translations.fa.movie.dubbed).not.toBe('دوبله');
    expect(translations.ps.movie.dubbed).toBe('ژباړل شوی');
    expect(translations.en.player.continue).toBe('Continue');
    expect(translations.en.player.startOver).toBe('Start Over');
  });
});
