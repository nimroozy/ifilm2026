import { cn } from '@/lib/utils';

export type CastCredit = {
  personId?: number;
  name: string;
  character?: string;
  profileUrl?: string;
  order?: number;
};

export function CastCard({ credit }: { credit: CastCredit }) {
  const initials = credit.name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
  return (
    <div
      className="flex w-[104px] shrink-0 flex-col gap-2 text-start sm:w-[120px]"
      data-testid="cast-card"
    >
      {credit.profileUrl ? (
        <img
          src={credit.profileUrl}
          alt=""
          className="aspect-[2/3] w-full rounded-xl object-cover ring-1 ring-white/10"
          loading="lazy"
          decoding="async"
        />
      ) : (
        <div className="flex aspect-[2/3] w-full items-center justify-center rounded-xl bg-gradient-to-br from-primary/30 to-secondary text-sm font-semibold text-foreground ring-1 ring-white/10 sm:text-base">
          {initials || '?'}
        </div>
      )}
      <div className="space-y-0.5">
        <p className="line-clamp-2 text-xs font-medium text-foreground sm:text-sm">{credit.name}</p>
        {credit.character ? (
          <p className="line-clamp-2 text-[11px] text-muted-foreground sm:text-xs">{credit.character}</p>
        ) : null}
      </div>
    </div>
  );
}

export function CastRail({
  credits,
  dir,
  headingId,
  title,
  titleClassName,
  testId,
  railTestId,
}: {
  credits: CastCredit[];
  dir?: 'ltr' | 'rtl';
  headingId: string;
  title: string;
  titleClassName?: string;
  testId?: string;
  railTestId?: string;
}) {
  if (!credits.length) return null;
  return (
    <section
      className="container mx-auto max-w-6xl px-4 sm:px-6 lg:px-8"
      aria-labelledby={headingId}
      data-testid={testId}
    >
      <h2 id={headingId} className={cn(titleClassName, 'mb-5')}>
        {title}
      </h2>
      <div
        className="flex gap-4 overflow-x-auto pb-2 hide-scrollbar sm:gap-5"
        dir={dir}
        data-testid={railTestId}
        tabIndex={0}
        role="list"
        aria-label={title}
      >
        {credits.map((person, index) => (
          <div key={`${person.personId ?? person.name}-${index}`} role="listitem">
            <CastCard credit={person} />
          </div>
        ))}
      </div>
    </section>
  );
}
