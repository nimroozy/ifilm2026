import * as React from 'react';
import { cn } from '@/lib/utils';
import { typography } from '@/design-system/tokens';

export interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  className?: string;
  as?: 'h2' | 'h3';
}

export function SectionHeader({
  title,
  subtitle,
  action,
  className,
  as: Tag = 'h2',
}: SectionHeaderProps) {
  return (
    <div
      className={cn(
        'mb-3 flex items-end justify-between gap-4 px-4 sm:px-6 lg:px-8 md:mb-4',
        className
      )}
    >
      <div className="min-w-0">
        <Tag className={cn(typography.sectionTitle, 'text-foreground')}>{title}</Tag>
        {subtitle ? <p className={cn(typography.meta, 'mt-1')}>{subtitle}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
