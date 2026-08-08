import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { adminApi } from '@/lib/adminApi';
import {
  ApiError,
  type ContentRequestAdminDetailDto,
  type ContentRequestAggregateDto,
  type ContentRequestDto,
} from '@/lib/api';

const STATUSES = ['', 'new', 'reviewing', 'approved', 'rejected', 'added', 'withdrawn'] as const;

export default function ContentRequestsAdminPage() {
  const [status, setStatus] = useState('');
  const [requestType, setRequestType] = useState('');
  const [q, setQ] = useState('');
  const [items, setItems] = useState<ContentRequestDto[]>([]);
  const [aggregates, setAggregates] = useState<ContentRequestAggregateDto[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ContentRequestAdminDetailDto | null>(null);
  const [adminNote, setAdminNote] = useState('');
  const [publicResponse, setPublicResponse] = useState('');
  const [linkId, setLinkId] = useState('');
  const [actionBusy, setActionBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminApi.listContentRequests({
        status: status || undefined,
        request_type: requestType || undefined,
        q: q.trim() || undefined,
        page: 1,
        page_size: 50,
      });
      setItems(data.items);
      setAggregates(data.aggregates || []);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load content requests');
    } finally {
      setLoading(false);
    }
  }, [q, requestType, status]);

  useEffect(() => {
    void load();
  }, [load]);

  const openDetail = async (id: number) => {
    setSelectedId(id);
    setError(null);
    try {
      const data = await adminApi.getContentRequest(id);
      setDetail(data);
      setAdminNote(data.request.admin_note || '');
      setPublicResponse(data.request.public_response || '');
      setLinkId(
        String(data.request.linked_movie_id || data.request.linked_series_id || '')
      );
    } catch (err) {
      setDetail(null);
      setError(err instanceof ApiError ? err.message : 'Failed to load request');
    }
  };

  const runAction = async (
    action: 'review' | 'approve' | 'reject' | 'mark_added' | 'reopen'
  ) => {
    if (!selectedId || !detail) return;
    setActionBusy(true);
    setError(null);
    try {
      const body: Parameters<typeof adminApi.contentRequestAction>[1] = {
        action,
        admin_note: adminNote || undefined,
        public_response: publicResponse || undefined,
      };
      if (action === 'mark_added') {
        const id = Number(linkId);
        if (!Number.isFinite(id) || id < 1) {
          setError('Link a catalog movie/series id before marking added');
          setActionBusy(false);
          return;
        }
        if (detail.request.request_type === 'movie') body.linked_movie_id = id;
        else body.linked_series_id = id;
      }
      await adminApi.contentRequestAction(selectedId, body);
      await load();
      await openDetail(selectedId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed');
    } finally {
      setActionBusy(false);
    }
  };

  const onFilter = (event: FormEvent) => {
    event.preventDefault();
    void load();
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6" data-testid="admin-content-requests">
      <div>
        <h1 className="text-2xl font-semibold">Content Requests</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Review subscriber movie/series requests. Linking a catalog item does not auto-import TMDB.
        </p>
      </div>

      <form onSubmit={onFilter} className="flex flex-wrap items-end gap-3" data-testid="cr-filters">
        <div className="space-y-1.5">
          <Label htmlFor="cr-status">Status</Label>
          <select
            id="cr-status"
            className="flex h-10 w-40 rounded-md border border-input bg-background px-3 text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            data-testid="cr-filter-status"
          >
            {STATUSES.map((s) => (
              <option key={s || 'all'} value={s}>
                {s || 'All'}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cr-type">Type</Label>
          <select
            id="cr-type"
            className="flex h-10 w-36 rounded-md border border-input bg-background px-3 text-sm"
            value={requestType}
            onChange={(e) => setRequestType(e.target.value)}
            data-testid="cr-filter-type"
          >
            <option value="">All</option>
            <option value="movie">Movie</option>
            <option value="series">Series</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cr-q">Search</Label>
          <Input
            id="cr-q"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Title or IMDb"
            className="w-56"
            data-testid="cr-filter-q"
          />
        </div>
        <Button type="submit" data-testid="cr-filter-submit">
          Apply
        </Button>
      </form>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground" data-testid="cr-total">
            {loading ? 'Loading…' : `${total} request(s)`}
          </p>
          <ul className="space-y-2" data-testid="cr-list">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => void openDetail(item.id)}
                  className={`w-full rounded-lg border px-3 py-3 text-start text-sm transition-colors ${
                    selectedId === item.id ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/40'
                  }`}
                  data-testid={`cr-row-${item.id}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">
                      {item.title}
                      {item.year ? ` (${item.year})` : ''}
                    </span>
                    <span className="text-xs uppercase tracking-wide text-muted-foreground">
                      {item.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {item.request_type} · @{item.subscriber_username || item.subscriber_id} · demand{' '}
                    {item.demand_count ?? 1}
                    {item.preferred_language ? ` · ${item.preferred_language}` : ''}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {item.created_at ? new Date(item.created_at).toLocaleString() : ''}
                    {item.tmdb_id ? ` · TMDB ${item.tmdb_id}` : ''}
                    {item.imdb_id ? ` · ${item.imdb_id}` : ''}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-4">
          {detail ? (
            <div className="rounded-lg border p-4 space-y-3" data-testid="cr-detail">
              <h2 className="text-lg font-semibold">{detail.request.title}</h2>
              <p className="text-sm text-muted-foreground">
                Status: {detail.request.status} · Type: {detail.request.request_type}
              </p>
              {detail.request.notes ? (
                <p className="text-sm">Notes: {detail.request.notes}</p>
              ) : null}
              <div className="space-y-1.5">
                <Label htmlFor="cr-admin-note">Admin note (private)</Label>
                <Textarea
                  id="cr-admin-note"
                  value={adminNote}
                  onChange={(e) => setAdminNote(e.target.value)}
                  data-testid="cr-admin-note"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cr-public-response">Public response</Label>
                <Input
                  id="cr-public-response"
                  value={publicResponse}
                  onChange={(e) => setPublicResponse(e.target.value)}
                  data-testid="cr-public-response"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cr-link-id">
                  Link catalog {detail.request.request_type} id
                </Label>
                <Input
                  id="cr-link-id"
                  value={linkId}
                  onChange={(e) => setLinkId(e.target.value)}
                  inputMode="numeric"
                  data-testid="cr-link-id"
                />
                <p className="text-xs text-muted-foreground">
                  Use an existing catalog id from Movies/Series admin. Does not import from TMDB.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={actionBusy}
                  onClick={() => void runAction('review')}
                  data-testid="cr-action-review"
                >
                  Review
                </Button>
                <Button
                  type="button"
                  size="sm"
                  disabled={actionBusy}
                  onClick={() => void runAction('approve')}
                  data-testid="cr-action-approve"
                >
                  Approve
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="destructive"
                  disabled={actionBusy}
                  onClick={() => void runAction('reject')}
                  data-testid="cr-action-reject"
                >
                  Reject
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={actionBusy}
                  onClick={() => void runAction('mark_added')}
                  data-testid="cr-action-mark-added"
                >
                  Mark Added
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={actionBusy}
                  onClick={() => void runAction('reopen')}
                  data-testid="cr-action-reopen"
                >
                  Reopen
                </Button>
              </div>
              {detail.request.linked_detail_path ? (
                <Link
                  to={detail.request.linked_detail_path}
                  className="text-sm text-primary underline-offset-4 hover:underline"
                >
                  Open linked title
                </Link>
              ) : null}
              <div>
                <h3 className="text-sm font-medium">Audit events</h3>
                <ul className="mt-2 max-h-48 space-y-1 overflow-auto text-xs text-muted-foreground">
                  {detail.events.map((ev) => (
                    <li key={ev.id}>
                      {ev.created_at}: {ev.event_type} {ev.from_status || '—'} → {ev.to_status || '—'}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Select a request to review.</p>
          )}

          <div className="rounded-lg border p-4" data-testid="cr-aggregates">
            <h2 className="text-base font-semibold">Aggregate demand</h2>
            <ul className="mt-3 space-y-2 text-sm">
              {aggregates.slice(0, 12).map((agg) => (
                <li key={`${agg.request_type}-${agg.normalized_title}-${agg.year}-${agg.tmdb_id}`}>
                  <span className="font-medium">{agg.title}</span>
                  {agg.year ? ` (${agg.year})` : ''}
                  <span className="text-muted-foreground">
                    {' '}
                    — Requested by {agg.request_count} user{agg.request_count === 1 ? '' : 's'}
                  </span>
                </li>
              ))}
              {aggregates.length === 0 ? (
                <li className="text-muted-foreground">No demand data yet.</li>
              ) : null}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
