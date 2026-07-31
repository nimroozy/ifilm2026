import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PublishingPanel from '../PublishingPanel';
import type { PublicationReadinessDto } from '@/lib/api';

const getPublicationReadiness = vi.fn();
const getPublicationHistory = vi.fn();
const submitReview = vi.fn();
const approve = vi.fn();
const publish = vi.fn();
const schedule = vi.fn();
const unpublish = vi.fn();
const archive = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      getPublicationReadiness: (...args: unknown[]) => getPublicationReadiness(...args),
      getPublicationHistory: (...args: unknown[]) => getPublicationHistory(...args),
      submitReview: (...args: unknown[]) => submitReview(...args),
      approve: (...args: unknown[]) => approve(...args),
      publish: (...args: unknown[]) => publish(...args),
      schedule: (...args: unknown[]) => schedule(...args),
      unpublish: (...args: unknown[]) => unpublish(...args),
      archive: (...args: unknown[]) => archive(...args),
    },
  };
});

function readiness(overrides: Partial<PublicationReadinessDto> = {}): PublicationReadinessDto {
  return {
    entity_type: 'movie',
    entity_id: 7,
    status: 'draft',
    ready: false,
    playable: false,
    active_package_id: null,
    package_status: null,
    issues: [],
    allowed_actions: [],
    publication_version: 1,
    ...overrides,
  };
}

function renderPanel(onChanged = vi.fn()) {
  render(
    <MemoryRouter>
      <PublishingPanel
        entityType="movie"
        entityId={7}
        currentStatus="draft"
        onChanged={onChanged}
      />
    </MemoryRouter>
  );
  return onChanged;
}

describe('PublishingPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getPublicationHistory.mockResolvedValue([]);
    submitReview.mockResolvedValue({
      detail: 'ok',
      entity_type: 'movie',
      entity_id: 7,
      status: 'in_review',
      publication_version: 2,
    });
    approve.mockResolvedValue({
      detail: 'ok',
      entity_type: 'movie',
      entity_id: 7,
      status: 'approved',
      publication_version: 2,
    });
    publish.mockResolvedValue({
      detail: 'ok',
      entity_type: 'movie',
      entity_id: 7,
      status: 'published',
      publication_version: 2,
    });
  });

  it('renders the workflow status badge', async () => {
    getPublicationReadiness.mockResolvedValue(readiness({ status: 'in_review' }));

    renderPanel();

    expect(await screen.findByText('In review')).toBeInTheDocument();
  });

  it('shows readiness failures returned by the backend', async () => {
    getPublicationReadiness.mockResolvedValue(
      readiness({
        issues: [
          { code: 'missing_title', message: 'A title is required', field: 'title' },
          { code: 'no_active_package', message: 'No active media package is available' },
        ],
      })
    );

    renderPanel();

    expect(await screen.findByTestId('readiness-issues')).toHaveTextContent('A title is required');
    expect(screen.getByTestId('readiness-issues')).toHaveTextContent(
      'No active media package is available'
    );
  });

  it('disables actions not included in allowed_actions', async () => {
    getPublicationReadiness.mockResolvedValue(
      readiness({ allowed_actions: ['submit_review'] })
    );

    renderPanel();

    expect(await screen.findByRole('button', { name: 'Submit for Review' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Publish' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Unpublish' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Archive' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Schedule' })).toBeDisabled();
  });

  it('asks for confirmation before publishing', async () => {
    getPublicationReadiness
      .mockResolvedValueOnce(readiness({ status: 'approved', ready: true, allowed_actions: ['publish'] }))
      .mockResolvedValueOnce(readiness({ status: 'published', ready: true, allowed_actions: ['unpublish'] }));
    const onChanged = renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Publish' }));

    expect(publish).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: 'Publish this movie?' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Publish' }));

    await waitFor(() => {
      expect(publish).toHaveBeenCalledWith('movie', 7);
    });
    expect(onChanged).toHaveBeenCalledWith('published');
  });
});
