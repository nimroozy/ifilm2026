import { FormEvent, useState } from 'react';
import { Search } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { adminApi, ApiError, type RecommendationInspectDto } from '@/lib/api';

/**
 * Restricted debug tool for recommendation ranking — not a surveillance dashboard.
 * Requires movies.read. Does not show auth/session secrets.
 */
export default function RecommendationsInspectPage() {
  const [subscriberId, setSubscriberId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecommendationInspectDto | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const id = Number(subscriberId);
    if (!Number.isFinite(id) || id < 1) {
      setError('Enter a valid subscriber ID');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await adminApi.inspectRecommendations(id, 20);
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(err instanceof ApiError ? err.message : 'Inspection failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 sm:p-6" data-testid="admin-rec-inspect">
      <div>
        <h1 className="text-2xl font-semibold">Recommendation Inspect</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Debug preference signals and ranked candidates for a subscriber. History shown is limited to
          aggregate signals used for recommendations — not a full surveillance view.
        </p>
      </div>

      <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="subscriber-id">Subscriber ID</Label>
          <Input
            id="subscriber-id"
            inputMode="numeric"
            value={subscriberId}
            onChange={(e) => setSubscriberId(e.target.value)}
            placeholder="e.g. 42"
            className="w-48"
            data-testid="rec-inspect-subscriber-id"
          />
        </div>
        <Button type="submit" disabled={loading} data-testid="rec-inspect-submit">
          <Search className="me-2 h-4 w-4" />
          {loading ? 'Loading…' : 'Inspect'}
        </Button>
      </form>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {result ? (
        <div className="space-y-4" data-testid="rec-inspect-result">
          <div className="rounded-lg border p-4 text-sm">
            <p>
              <span className="text-muted-foreground">User:</span> {result.username} (#{result.subscriber_id})
            </p>
            <p>
              <span className="text-muted-foreground">Mode:</span> {result.mode}
            </p>
          </div>

          <div className="rounded-lg border p-4">
            <h2 className="mb-2 font-medium">Top preference signals</h2>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
              {JSON.stringify(result.preference_signals, null, 2)}
            </pre>
          </div>

          <div className="rounded-lg border p-4">
            <h2 className="mb-2 font-medium">Weights</h2>
            <pre className="overflow-auto text-xs text-muted-foreground">
              {JSON.stringify(result.weights, null, 2)}
            </pre>
          </div>

          <div className="space-y-3">
            <h2 className="font-medium">Ranked candidates</h2>
            {(result.candidates || []).map((item, index) => (
              <div
                key={`${item.content_type}-${item.id}`}
                className="rounded-lg border p-3 text-sm"
                data-testid={`rec-inspect-candidate-${item.id}`}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="font-medium">
                    #{index + 1} {item.title}{' '}
                    <span className="text-muted-foreground">
                      ({item.content_type} · {item.id})
                    </span>
                  </p>
                  <p className="tabular-nums text-muted-foreground">score {item.score.toFixed(3)}</p>
                </div>
                <ul className="mt-1 list-inside list-disc text-muted-foreground">
                  {item.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
                {item.components ? (
                  <pre className="mt-2 text-xs text-muted-foreground">
                    {JSON.stringify(item.components)}
                  </pre>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
