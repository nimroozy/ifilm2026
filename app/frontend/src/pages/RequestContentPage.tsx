import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useAuth, useLang } from '@/components/CustomerLayout';
import {
  api,
  ApiError,
  type CatalogMatchDto,
  type ContentRequestCreateResult,
  type ContentRequestDto,
  type MovieDto,
  type SeriesDto,
} from '@/lib/api';
import { cn } from '@/lib/utils';

type RequestCopy = {
  title: string;
  subtitle: string;
  disclaimer: string;
  typeLabel: string;
  movie: string;
  series: string;
  titleLabel: string;
  yearLabel: string;
  tmdbLabel: string;
  imdbLabel: string;
  languageLabel: string;
  notesLabel: string;
  submit: string;
  submitting: string;
  signInPrompt: string;
  signIn: string;
  myRequests: string;
  emptyRequests: string;
  status: string;
  requested: string;
  preferredLanguage: string;
  response: string;
  availableNow: string;
  viewTitle: string;
  withdraw: string;
  alreadyAvailable: string;
  existingRequest: string;
  suggestionsTitle: string;
  continueAnyway: string;
  catalogHint: string;
  success: string;
  errorGeneric: string;
  rateLimited: string;
  statuses: Record<string, string>;
};

function statusLabel(copy: RequestCopy, status: string): string {
  return copy.statuses[status] || status;
}

export default function RequestContentPage() {
  const { t, lang } = useLang();
  const { isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const copy = t.requestContent as RequestCopy;

  const [requestType, setRequestType] = useState<'movie' | 'series'>('movie');
  const [title, setTitle] = useState('');
  const [year, setYear] = useState('');
  const [tmdbUrl, setTmdbUrl] = useState('');
  const [imdbUrl, setImdbUrl] = useState('');
  const [preferredLanguage, setPreferredLanguage] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [createResult, setCreateResult] = useState<ContentRequestCreateResult | null>(null);
  const [requests, setRequests] = useState<ContentRequestDto[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [catalogHits, setCatalogHits] = useState<Array<MovieDto | SeriesDto>>([]);

  const loadRequests = useCallback(async () => {
    if (!isLoggedIn) {
      setRequests([]);
      return;
    }
    try {
      const result = await api.listContentRequests({ page: 1, page_size: 50 });
      setRequests(result.items);
      setListError(null);
    } catch (err) {
      setListError(err instanceof ApiError ? err.message : copy.errorGeneric);
    }
  }, [copy.errorGeneric, isLoggedIn]);

  useEffect(() => {
    void loadRequests();
  }, [loadRequests]);

  useEffect(() => {
    if (!title.trim() || title.trim().length < 2) {
      setCatalogHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void api
        .search(title.trim(), lang)
        .then((res) => {
          const movies = (res.movies || []).slice(0, 3);
          const series = (res.series || []).slice(0, 3);
          setCatalogHits(requestType === 'movie' ? movies : series);
        })
        .catch(() => setCatalogHits([]));
    }, 350);
    return () => window.clearTimeout(handle);
  }, [title, requestType, lang]);

  const yearNumber = useMemo(() => {
    if (!year.trim()) return undefined;
    const n = Number(year);
    return Number.isFinite(n) ? n : undefined;
  }, [year]);

  const submit = async (force = false) => {
    setSubmitting(true);
    setFormError(null);
    setFormMessage(null);
    try {
      const result = await api.createContentRequest({
        request_type: requestType,
        title: title.trim(),
        year: yearNumber,
        tmdb_url: tmdbUrl.trim() || undefined,
        imdb_url: imdbUrl.trim() || undefined,
        preferred_language: preferredLanguage.trim() || undefined,
        notes: notes.trim() || undefined,
        force,
      });
      setCreateResult(result);
      if (result.outcome === 'created') {
        setFormMessage(copy.success);
        setTitle('');
        setYear('');
        setTmdbUrl('');
        setImdbUrl('');
        setPreferredLanguage('');
        setNotes('');
        await loadRequests();
      } else if (result.outcome === 'already_available') {
        setFormMessage(copy.alreadyAvailable);
      } else if (result.outcome === 'existing_request') {
        setFormMessage(copy.existingRequest);
        await loadRequests();
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setFormError(copy.rateLimited);
      } else {
        setFormError(err instanceof ApiError ? err.message : copy.errorGeneric);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) {
      setFormError(copy.titleLabel);
      return;
    }
    void submit(false);
  };

  const withdraw = async (id: number) => {
    try {
      await api.withdrawContentRequest(id);
      await loadRequests();
    } catch (err) {
      setListError(err instanceof ApiError ? err.message : copy.errorGeneric);
    }
  };

  if (!isLoggedIn) {
    return (
      <div className="container mx-auto max-w-2xl px-4 py-10" data-testid="request-content-page">
        <h1 className="font-display text-3xl font-bold text-foreground">{copy.title}</h1>
        <p className="mt-3 text-muted-foreground">{copy.signInPrompt}</p>
        <Button className="mt-6" onClick={() => navigate('/login?next=/request')} data-testid="request-sign-in">
          {copy.signIn}
        </Button>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-3xl px-4 py-8 sm:px-6" data-testid="request-content-page">
      <header className="mb-8">
        <h1 className="font-display text-3xl font-bold tracking-tight text-foreground md:text-4xl">
          {copy.title}
        </h1>
        <p className="mt-2 text-muted-foreground">{copy.subtitle}</p>
        <p className="mt-3 text-sm text-foreground/80" data-testid="request-disclaimer">
          {copy.disclaimer}
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-5" data-testid="request-form" noValidate>
        <fieldset>
          <legend className="mb-2 text-sm font-medium">{copy.typeLabel}</legend>
          <div className="flex flex-wrap gap-2">
            {(['movie', 'series'] as const).map((type) => (
              <button
                key={type}
                type="button"
                data-testid={`request-type-${type}`}
                aria-pressed={requestType === type}
                onClick={() => setRequestType(type)}
                className={cn(
                  'rounded-lg border px-4 py-2 text-sm font-medium transition-colors',
                  requestType === type
                    ? 'border-primary bg-primary/10 text-foreground'
                    : 'border-border text-muted-foreground hover:border-primary/40'
                )}
              >
                {type === 'movie' ? copy.movie : copy.series}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="space-y-2">
          <Label htmlFor="request-title">{copy.titleLabel}</Label>
          <Input
            id="request-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={255}
            data-testid="request-title"
            autoComplete="off"
          />
        </div>

        {catalogHits.length > 0 ? (
          <div
            className="rounded-lg border border-border/70 bg-muted/20 p-3 text-sm"
            data-testid="request-catalog-suggestions"
          >
            <p className="mb-2 font-medium">{copy.catalogHint}</p>
            <ul className="space-y-2">
              {catalogHits.map((item) => {
                const path =
                  'duration_minutes' in item || requestType === 'movie'
                    ? `/movie/${item.slug || item.id}`
                    : `/series/${item.slug || item.id}`;
                const yearLabel = item.release_year;
                return (
                  <li key={`${requestType}-${item.id}`} className="flex flex-wrap items-center justify-between gap-2">
                    <span>
                      {item.title}
                      {yearLabel ? ` (${yearLabel})` : ''}
                    </span>
                    <Link to={path} className="text-primary underline-offset-4 hover:underline">
                      {copy.viewTitle}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="request-year">{copy.yearLabel}</Label>
            <Input
              id="request-year"
              inputMode="numeric"
              value={year}
              onChange={(e) => setYear(e.target.value)}
              data-testid="request-year"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="request-language">{copy.languageLabel}</Label>
            <Input
              id="request-language"
              value={preferredLanguage}
              onChange={(e) => setPreferredLanguage(e.target.value)}
              data-testid="request-language"
            />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="request-tmdb">{copy.tmdbLabel}</Label>
            <Input
              id="request-tmdb"
              value={tmdbUrl}
              onChange={(e) => setTmdbUrl(e.target.value)}
              placeholder="https://www.themoviedb.org/movie/…"
              data-testid="request-tmdb"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="request-imdb">{copy.imdbLabel}</Label>
            <Input
              id="request-imdb"
              value={imdbUrl}
              onChange={(e) => setImdbUrl(e.target.value)}
              placeholder="https://www.imdb.com/title/tt…"
              data-testid="request-imdb"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="request-notes">{copy.notesLabel}</Label>
          <Textarea
            id="request-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={2000}
            rows={3}
            data-testid="request-notes"
          />
        </div>

        {formError ? (
          <Alert variant="destructive" data-testid="request-form-error">
            <AlertTitle>{copy.errorGeneric}</AlertTitle>
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        ) : null}
        {formMessage ? (
          <Alert data-testid="request-form-message">
            <AlertDescription>{formMessage}</AlertDescription>
          </Alert>
        ) : null}

        {createResult?.outcome === 'already_available' && createResult.catalog_item ? (
          <CatalogMatchCard item={createResult.catalog_item} label={copy.viewTitle} />
        ) : null}

        {createResult?.outcome === 'suggestions' && createResult.suggestions.length > 0 ? (
          <div className="space-y-3 rounded-lg border p-4" data-testid="request-suggestions">
            <p className="text-sm font-medium">{copy.suggestionsTitle}</p>
            <ul className="space-y-2">
              {createResult.suggestions.map((item) => (
                <li key={`${item.content_type}-${item.id}`}>
                  <CatalogMatchCard item={item} label={copy.viewTitle} />
                </li>
              ))}
            </ul>
            <Button
              type="button"
              variant="secondary"
              onClick={() => void submit(true)}
              disabled={submitting}
              data-testid="request-force-continue"
            >
              {copy.continueAnyway}
            </Button>
          </div>
        ) : null}

        <Button type="submit" disabled={submitting} data-testid="request-submit">
          {submitting ? copy.submitting : copy.submit}
        </Button>
      </form>

      <section className="mt-12" data-testid="my-requests">
        <h2 className="font-display text-2xl font-semibold">{copy.myRequests}</h2>
        {listError ? <p className="mt-2 text-sm text-destructive">{listError}</p> : null}
        {requests.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">{copy.emptyRequests}</p>
        ) : (
          <ul className="mt-4 space-y-3">
            {requests.map((req) => (
              <li
                key={req.id}
                className="rounded-lg border border-border/70 px-4 py-3"
                data-testid={`my-request-${req.id}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-foreground">
                      {req.title}
                      {req.year ? ` (${req.year})` : ''}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {req.request_type === 'movie' ? copy.movie : copy.series}
                      {' · '}
                      {copy.requested}: {new Date(req.created_at).toLocaleDateString(lang)}
                      {' · '}
                      {copy.status}: {statusLabel(copy, req.status)}
                    </p>
                    {req.preferred_language ? (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {copy.preferredLanguage}: {req.preferred_language}
                      </p>
                    ) : null}
                    {req.public_response ? (
                      <p className="mt-1 text-sm text-foreground/90">
                        {copy.response}: {req.public_response}
                      </p>
                    ) : null}
                    {req.status === 'added' && req.linked_detail_path ? (
                      <Link
                        to={req.linked_detail_path}
                        className="mt-2 inline-block text-sm text-primary underline-offset-4 hover:underline"
                        data-testid={`my-request-link-${req.id}`}
                      >
                        {copy.availableNow}
                        {req.linked_title ? ` — ${req.linked_title}` : ''}
                      </Link>
                    ) : null}
                  </div>
                  {req.status === 'new' || req.status === 'reviewing' ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => void withdraw(req.id)}
                      data-testid={`request-withdraw-${req.id}`}
                    >
                      {copy.withdraw}
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function CatalogMatchCard({ item, label }: { item: CatalogMatchDto; label: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-sm" data-testid="catalog-match">
      <span>
        {item.title}
        {item.release_year ? ` (${item.release_year})` : ''}
      </span>
      <Link to={item.detail_path} className="text-primary underline-offset-4 hover:underline">
        {label}
      </Link>
    </div>
  );
}
