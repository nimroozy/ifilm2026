import { cn } from '@/lib/utils';

/** Shared motion class presets — respect prefers-reduced-motion via global CSS. */
export const motionPresets = {
  fadeIn: 'animate-fade-in',
  slideUp: 'animate-slide-up',
  scaleIn: 'animate-scale-in',
  liftIn: 'animate-lift-in',
  press: 'active:scale-[0.98] transition-transform duration-fast',
  hoverLift: 'transition-transform duration-normal ease-out hover:-translate-y-1',
  hoverGlow: 'transition-shadow duration-normal hover:shadow-xl',
  softEnter: 'animate-lift-in motion-safe:opacity-0',
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
