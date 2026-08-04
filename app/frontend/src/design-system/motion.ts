import { cn } from '@/lib/utils';

/**
 * Shared motion class presets — minimal, reusable.
 * Global `prefers-reduced-motion` in index.css collapses animation/transition durations.
 * Do not pair these with a sticky `opacity-0` that can leave content invisible if animation never runs.
 */
export const motionPresets = {
  fadeIn: 'animate-fade-in',
  slideUp: 'animate-slide-up',
  scaleIn: 'animate-scale-in',
  liftIn: 'animate-lift-in',
  press: 'active:scale-[0.98] transition-transform duration-fast',
  hoverLift: 'transition-transform duration-normal ease-out hover:-translate-y-1',
  hoverGlow: 'transition-shadow duration-normal hover:shadow-xl',
  /** Opacity-only enter — visible by default if animation does not run. */
  softEnter: 'animate-fade-in',
} as const;

export function motionClass(
  ...parts: Array<keyof typeof motionPresets | string | false | null | undefined>
): string {
  return cn(
    ...parts.map((part) =>
      part && part in motionPresets ? motionPresets[part as keyof typeof motionPresets] : part
    )
  );
}
