import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useLang } from '@/components/CustomerLayout';
import { ContentShelf, MediaCard } from '@/design-system';
import { api, ApiError, type RecommendationItemDto, type WhatToWatchBody } from '@/lib/api';
import {
  localizeRecommendationExplanation,
  localizeRelaxedNotes,
} from '@/lib/recommendationI18n';
import { cn } from '@/lib/utils';

type StepId = 'type' | 'genre' | 'mood' | 'duration' | 'language' | 'subtitles' | 'period' | 'results';

const STEPS: StepId[] = ['type', 'genre', 'mood', 'duration', 'language', 'subtitles', 'period', 'results'];

type Choice = { value: string; labelKey: string };

function ChoiceGrid({
  options,
  value,
  onChange,
  testId,
}: {
  options: Choice[];
  value: string | null;
  onChange: (v: string) => void;
  testId: string;
}) {
  const { t } = useLang();
  const labels = t.whatToWatch as Record<string, string>;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" data-testid={testId}>
      {options.map((opt) => {
        const selected = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            data-testid={`${testId}-${opt.value}`}
            aria-pressed={selected}
            onClick={() => onChange(opt.value)}
            className={cn(
              'rounded-xl border px-3 py-4 text-start text-sm font-medium transition-all duration-200',
              'hover:border-primary/50 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
              selected
                ? 'border-primary bg-primary/10 text-foreground shadow-sm scale-[1.02]'
                : 'border-border/60 bg-background/40 text-foreground/80'
            )}
          >
            {labels[opt.labelKey] || opt.value}
          </button>
        );
      })}
    </div>
  );
}

export default function WhatToWatchPage() {
  const { t, lang } = useLang();
  const navigate = useNavigate();
  const w = t.whatToWatch;
  const [stepIndex, setStepIndex] = useState(0);
  const [contentType, setContentType] = useState<string | null>(null);
  const [genre, setGenre] = useState<string | null>(null);
  const [mood, setMood] = useState<string | null>(null);
  const [duration, setDuration] = useState<string | null>(null);
  const [language, setLanguage] = useState<string | null>(null);
  const [subtitles, setSubtitles] = useState<string | null>(null);
  const [period, setPeriod] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<RecommendationItemDto[] | null>(null);
  const [relaxed, setRelaxed] = useState<string[]>([]);

  const step = STEPS[stepIndex];

  const reset = () => {
    setStepIndex(0);
    setContentType(null);
    setGenre(null);
    setMood(null);
    setDuration(null);
    setLanguage(null);
    setSubtitles(null);
    setPeriod(null);
    setItems(null);
    setRelaxed([]);
    setError(null);
    setLoading(false);
  };

  const runSearch = async (overrides?: Partial<WhatToWatchBody>) => {
    setLoading(true);
    setError(null);
    try {
      const body: WhatToWatchBody = {
        content_type: (overrides?.content_type || contentType || 'either') as WhatToWatchBody['content_type'],
        genre: overrides?.genre ?? (genre && genre !== 'any' ? genre : null),
        mood: overrides?.mood ?? (mood && mood !== 'any' ? mood : null),
        duration: (overrides?.duration || duration || 'any') as WhatToWatchBody['duration'],
        language: overrides?.language ?? (language || 'any'),
        subtitles: (overrides?.subtitles || subtitles || 'optional') as WhatToWatchBody['subtitles'],
        release_period: (overrides?.release_period || period || 'any') as WhatToWatchBody['release_period'],
        limit: 8,
      };
      const result = await api.whatToWatch(body);
      setItems(result.items);
      setRelaxed(result.relaxed || []);
      setStepIndex(STEPS.indexOf('results'));
    } catch (err) {
      setItems([]);
      setRelaxed([]);
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : w.error
      );
      setStepIndex(STEPS.indexOf('results'));
    } finally {
      setLoading(false);
    }
  };

  const advance = (nextValue: string, setter: (v: string) => void, then?: () => void) => {
    setter(nextValue);
    if (then) {
      then();
      return;
    }
    setStepIndex((i) => Math.min(i + 1, STEPS.length - 1));
  };

  const progressLabel = useMemo(() => {
    if (step === 'results') return w.results;
    return `${w.step} ${stepIndex + 1} / ${STEPS.length - 1}`;
  }, [step, stepIndex, w]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8" data-testid="what-to-watch-page">
      <header className="mb-8 space-y-2">
        <p className="text-sm font-medium text-primary/90">{w.eyebrow}</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">{w.title}</h1>
        <p className="max-w-xl text-muted-foreground">{w.subtitle}</p>
        <p className="text-xs text-muted-foreground/80" data-testid="wtw-progress">
          {progressLabel}
        </p>
      </header>

      {step === 'type' && (
        <section className="space-y-4" data-testid="wtw-step-type">
          <h2 className="text-lg font-medium">{w.askType}</h2>
          <ChoiceGrid
            testId="wtw-type"
            value={contentType}
            onChange={(v) => advance(v, setContentType)}
            options={[
              { value: 'movie', labelKey: 'typeMovie' },
              { value: 'series', labelKey: 'typeSeries' },
              { value: 'either', labelKey: 'typeEither' },
            ]}
          />
        </section>
      )}

      {step === 'genre' && (
        <section className="space-y-4" data-testid="wtw-step-genre">
          <h2 className="text-lg font-medium">{w.askGenre}</h2>
          <ChoiceGrid
            testId="wtw-genre"
            value={genre}
            onChange={(v) => advance(v, setGenre)}
            options={[
              { value: 'any', labelKey: 'any' },
              { value: 'Action', labelKey: 'genreAction' },
              { value: 'Comedy', labelKey: 'genreComedy' },
              { value: 'Drama', labelKey: 'genreDrama' },
              { value: 'Science Fiction', labelKey: 'genreSciFi' },
              { value: 'Family', labelKey: 'genreFamily' },
              { value: 'Thriller', labelKey: 'genreThriller' },
            ]}
          />
        </section>
      )}

      {step === 'mood' && (
        <section className="space-y-4" data-testid="wtw-step-mood">
          <h2 className="text-lg font-medium">{w.askMood}</h2>
          <ChoiceGrid
            testId="wtw-mood"
            value={mood}
            onChange={(v) => advance(v, setMood)}
            options={[
              { value: 'any', labelKey: 'any' },
              { value: 'exciting', labelKey: 'moodExciting' },
              { value: 'funny', labelKey: 'moodFunny' },
              { value: 'emotional', labelKey: 'moodEmotional' },
              { value: 'relaxing', labelKey: 'moodRelaxing' },
              { value: 'suspenseful', labelKey: 'moodSuspenseful' },
              { value: 'family', labelKey: 'moodFamily' },
            ]}
          />
        </section>
      )}

      {step === 'duration' && (
        <section className="space-y-4" data-testid="wtw-step-duration">
          <h2 className="text-lg font-medium">{w.askDuration}</h2>
          <ChoiceGrid
            testId="wtw-duration"
            value={duration}
            onChange={(v) => advance(v, setDuration)}
            options={[
              { value: 'any', labelKey: 'any' },
              { value: 'under_90', labelKey: 'durationShort' },
              { value: '90_120', labelKey: 'durationMedium' },
              { value: 'over_120', labelKey: 'durationLong' },
            ]}
          />
        </section>
      )}

      {step === 'language' && (
        <section className="space-y-4" data-testid="wtw-step-language">
          <h2 className="text-lg font-medium">{w.askLanguage}</h2>
          <ChoiceGrid
            testId="wtw-language"
            value={language}
            onChange={(v) => advance(v, setLanguage)}
            options={[
              { value: 'any', labelKey: 'any' },
              { value: 'original', labelKey: 'langOriginal' },
              { value: 'persian', labelKey: 'langPersian' },
              { value: 'pashto', labelKey: 'langPashto' },
            ]}
          />
        </section>
      )}

      {step === 'subtitles' && (
        <section className="space-y-4" data-testid="wtw-step-subtitles">
          <h2 className="text-lg font-medium">{w.askSubtitles}</h2>
          <ChoiceGrid
            testId="wtw-subtitles"
            value={subtitles}
            onChange={(v) => advance(v, setSubtitles)}
            options={[
              { value: 'optional', labelKey: 'subsOptional' },
              { value: 'required', labelKey: 'subsRequired' },
              { value: 'any', labelKey: 'any' },
            ]}
          />
        </section>
      )}

      {step === 'period' && (
        <section className="space-y-4" data-testid="wtw-step-period">
          <h2 className="text-lg font-medium">{w.askPeriod}</h2>
          <ChoiceGrid
            testId="wtw-period"
            value={period}
            onChange={(v) => {
              setPeriod(v);
              void runSearch({ release_period: v as WhatToWatchBody['release_period'] });
            }}
            options={[
              { value: 'any', labelKey: 'any' },
              { value: 'new', labelKey: 'periodNew' },
              { value: 'modern', labelKey: 'periodModern' },
              { value: 'classic', labelKey: 'periodClassic' },
            ]}
          />
        </section>
      )}

      {step === 'results' && (
        <section className="space-y-6" data-testid="wtw-results">
          {loading ? (
            <div className="space-y-3" data-testid="wtw-loading">
              <Skeleton className="h-7 w-48" />
              <div className="flex gap-4 overflow-hidden">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-[240px] w-[150px] shrink-0 rounded-xl" />
                ))}
              </div>
            </div>
          ) : error ? (
            <div className="space-y-3" role="alert" data-testid="wtw-error">
              <p className="text-muted-foreground">{error}</p>
              <Button onClick={() => void runSearch()}>{w.tryAgain}</Button>
            </div>
          ) : !items?.length ? (
            <div className="space-y-3" data-testid="wtw-empty">
              <p className="text-muted-foreground">{w.empty}</p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void runSearch()}>{w.tryAgain}</Button>
                <Button variant="outline" onClick={reset}>
                  {w.reset}
                </Button>
              </div>
            </div>
          ) : (
            <>
              {localizeRelaxedNotes(relaxed, lang, w as Record<string, string>) ? (
                <p className="text-sm text-muted-foreground" data-testid="wtw-relaxed">
                  {localizeRelaxedNotes(relaxed, lang, w as Record<string, string>)}
                </p>
              ) : null}
              <ContentShelf title={w.resultsTitle}>
                {items.map((item) => (
                  <MediaCard
                    key={`${item.content_type}-${item.id}`}
                    title={item.title}
                    imageUrl={item.poster_url}
                    year={item.release_year ?? undefined}
                    rating={item.imdb_rating ?? undefined}
                    playable={Boolean(item.playable)}
                    status={localizeRecommendationExplanation(item.explanation, lang)}
                    badge={item.content_type === 'series' ? 'Series' : undefined}
                    data-testid={`wtw-card-${item.id}`}
                    onActivate={() => navigate(item.detail_path)}
                  />
                ))}
              </ContentShelf>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={reset} data-testid="wtw-reset">
                  {w.reset}
                </Button>
                <Button onClick={() => void runSearch()} data-testid="wtw-try-again">
                  {w.tryAgain}
                </Button>
              </div>
            </>
          )}
        </section>
      )}

      {step !== 'results' && stepIndex > 0 ? (
        <div className="mt-8 flex flex-wrap gap-2">
          <Button
            variant="ghost"
            onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
            data-testid="wtw-back"
          >
            {w.back}
          </Button>
          <Button variant="outline" onClick={reset} data-testid="wtw-reset-early">
            {w.reset}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
