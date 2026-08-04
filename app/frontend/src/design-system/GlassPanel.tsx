import * as React from 'react';
import { cn } from '@/lib/utils';
import { surfaces } from '@/design-system/tokens';

export interface GlassPanelProps extends React.HTMLAttributes<HTMLDivElement> {
  strength?: 'default' | 'strong';
}

/** Frosted cinema chrome — player controls, floating actions, overlays. */
export function GlassPanel({
  className,
  strength = 'default',
  ...props
}: GlassPanelProps) {
  return (
    <div
      className={cn(
        strength === 'strong' ? surfaces.glassStrong : surfaces.glass,
        'rounded-xl',
        className
      )}
      {...props}
    />
  );
}
