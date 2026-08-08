/**
 * iFilm design tokens — spacing, type, motion, and status semantics.
 * Prefer these over ad-hoc Tailwind values for customer + admin surfaces.
 */

export const spacing = {
  0: '0',
  1: '0.25rem',
  2: '0.5rem',
  3: '0.75rem',
  4: '1rem',
  5: '1.25rem',
  6: '1.5rem',
  8: '2rem',
  10: '2.5rem',
  12: '3rem',
  16: '4rem',
  20: '5rem',
  24: '6rem',
} as const;

export const typography = {
  displayHero: 'font-display text-4xl font-bold tracking-tight md:text-6xl lg:text-7xl',
  displayTitle: 'font-display text-3xl font-bold tracking-tight md:text-5xl',
  sectionTitle: 'font-display text-xl font-bold tracking-tight md:text-2xl',
  cardTitle: 'font-sans text-sm font-semibold leading-snug md:text-base',
  body: 'font-sans text-base leading-relaxed text-foreground/90',
  bodySm: 'font-sans text-sm leading-relaxed text-foreground/85',
  meta: 'font-sans text-sm text-muted-foreground',
  metaSm: 'font-sans text-xs text-muted-foreground',
  eyebrow: 'font-sans text-xs font-semibold uppercase tracking-[0.2em] text-primary',
  label: 'font-sans text-xs font-medium uppercase tracking-wide text-muted-foreground',
} as const;

export const motion = {
  fast: 'duration-fast',
  normal: 'duration-normal',
  slow: 'duration-slow',
  easeOut: 'ease-out',
  hoverLift: 'transition-transform duration-normal ease-out hover:-translate-y-1',
  hoverScale: 'transition-transform duration-normal ease-out group-hover/card:scale-105',
  fade: 'animate-fade-in',
  slideUp: 'animate-slide-up',
} as const;

export const surfaces = {
  glass:
    'bg-background/55 backdrop-blur-xl border border-white/10 shadow-lg supports-[backdrop-filter]:bg-background/40',
  glassStrong:
    'bg-background/75 backdrop-blur-2xl border border-white/12 shadow-xl supports-[backdrop-filter]:bg-background/55',
  cinemaOverlay:
    'bg-gradient-to-t from-background via-background/70 to-transparent',
  cinemaSide:
    'bg-gradient-to-r from-background via-background/55 to-transparent',
  mediaCard:
    'rounded-xl overflow-hidden bg-muted shadow-md ring-1 ring-white/5',
} as const;

/**
 * Poster rail widths — premium streaming density (~190–230px desktop).
 * Target: ~5–6 cards at 1440, ~6–7 at 1920, 2 on mobile.
 */
export const mediaSizes = {
  posterSm: 'w-[156px] md:w-[190px]',
  posterMd: 'w-[168px] md:w-[210px] xl:w-[220px]',
  posterLg: 'w-[180px] md:w-[230px]',
  landscapeSm: 'w-[240px] md:w-[300px]',
  landscapeMd: 'w-[280px] md:w-[340px]',
} as const;

/** Shared browse/search/collection grid — larger cards, fewer per row. */
export const mediaGridClass =
  'grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-6';

export type StatusTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'gold';

export const statusToneClass: Record<StatusTone, string> = {
  neutral: 'bg-secondary text-secondary-foreground',
  success: 'bg-success text-success-foreground',
  warning: 'bg-warning text-warning-foreground',
  danger: 'bg-destructive text-destructive-foreground',
  info: 'bg-accent text-accent-foreground',
  gold: 'bg-primary text-primary-foreground',
};
