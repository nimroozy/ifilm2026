import type { PlayerStatsSnapshot } from './types';

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function StatsOverlay({
  open,
  stats,
  onClose,
}: {
  open: boolean;
  stats: PlayerStatsSnapshot | null;
  onClose: () => void;
}) {
  if (!open || !stats) return null;

  const rows: [string, string][] = [
    ['Resolution', stats.currentResolution],
    ['Rendition', stats.currentRendition],
    [
      'Bandwidth',
      stats.estimatedBandwidthMbps != null ? `${stats.estimatedBandwidthMbps.toFixed(2)} Mbps` : '—',
    ],
    [
      'Buffered',
      stats.bufferedSeconds != null ? `${stats.bufferedSeconds.toFixed(1)} s` : '—',
    ],
    ['Dropped frames', stats.droppedFrames != null ? String(stats.droppedFrames) : '—'],
    ['Time', `${formatTime(stats.currentTime)} / ${formatTime(stats.duration)}`],
    ['Rate', `${stats.playbackRate}x`],
    ['Video codec', stats.videoCodec || '—'],
    ['Audio codec', stats.audioCodec || '—'],
  ];

  return (
    <div
      className="absolute start-3 top-14 z-40 max-w-xs rounded-md border border-white/20 bg-black/85 p-3 font-mono text-[11px] text-white/90 shadow-lg backdrop-blur"
      data-testid="player-stats-overlay"
      role="region"
      aria-label="Playback diagnostics"
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-xs font-sans font-semibold tracking-wide text-white">Playback diagnostics</p>
        <button
          type="button"
          className="rounded px-1.5 py-0.5 text-white/70 hover:bg-white/10 hover:text-white"
          onClick={onClose}
          aria-label="Close diagnostics"
        >
          Esc
        </button>
      </div>
      <dl className="space-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[7.5rem_1fr] gap-2">
            <dt className="text-white/50">{label}</dt>
            <dd className="truncate" title={value}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-[10px] text-white/40">No stream URLs or tokens are shown.</p>
    </div>
  );
}
