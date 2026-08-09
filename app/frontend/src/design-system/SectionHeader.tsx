import * as React from 'react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { typography } from '@/design-system/tokens';

export interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  seeAllHref?: string;
  seeAllLabel?: string;
  className?: string;
  as?: 'h2' | 'h3';
}

export function SectionHeader({
  title,
  subtitle,
  action,
  seeAllHref,
  seeAllLabel = 'See all',
  className,
  as: Tag = 'h2',
}: SectionHeaderProps) {
  const trailing =
    action ??
    (seeAllHref ? (
      <Link
        to={seeAllHref}
        className="text-sm font-medium text-muted-foreground transition-colors hover:text-primary"
      >
        {seeAllLabel}
      </Link>
    ) : null);

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
      {trailing ? <div className="shrink-0">{trailing}</div> : null}
    </div>
  );
}
