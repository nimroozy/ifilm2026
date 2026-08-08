import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ContentRequestsAdminPage from '@/pages/admin/ContentRequestsAdminPage';

const listContentRequests = vi.fn();
const getContentRequest = vi.fn();
const contentRequestAction = vi.fn();

vi.mock('@/lib/api', () => ({
  adminApi: {
    listContentRequests: (...args: unknown[]) => listContentRequests(...args),
    getContentRequest: (...args: unknown[]) => getContentRequest(...args),
    contentRequestAction: (...args: unknown[]) => contentRequestAction(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status = 400) {
      super(message);
      this.status = status;
    }
  },
}));

describe('ContentRequestsAdminPage', () => {
  beforeEach(() => {
    listContentRequests.mockReset();
    getContentRequest.mockReset();
    contentRequestAction.mockReset();
    listContentRequests.mockResolvedValue({
      items: [
        {
          id: 3,
          request_type: 'movie',
          title: 'Dune Part Three',
          year: 2026,
          status: 'new',
          subscriber_username: 'alice',
          demand_count: 12,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
      aggregates: [
        {
          request_type: 'movie',
          title: 'Dune Part Three',
          normalized_title: 'dune part three',
          year: 2026,
          request_count: 12,
          open_count: 10,
          preferred_languages: { Dari: 5 },
        },
      ],
    });
  });

  it('renders queue, filters, and aggregate demand', async () => {
    render(
      <MemoryRouter>
        <ContentRequestsAdminPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByTestId('cr-row-3')).toBeInTheDocument());
    expect(screen.getByTestId('cr-filters')).toBeInTheDocument();
    expect(screen.getByTestId('cr-aggregates')).toHaveTextContent(/Requested by 12/);
  });

  it('opens detail and runs approve action', async () => {
    getContentRequest.mockResolvedValue({
      request: {
        id: 3,
        request_type: 'movie',
        title: 'Dune Part Three',
        status: 'new',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      events: [],
    });
    contentRequestAction.mockResolvedValue({
      id: 3,
      request_type: 'movie',
      title: 'Dune Part Three',
      status: 'approved',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    render(
      <MemoryRouter>
        <ContentRequestsAdminPage />
      </MemoryRouter>
    );
    fireEvent.click(await screen.findByTestId('cr-row-3'));
    await waitFor(() => expect(screen.getByTestId('cr-detail')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('cr-action-approve'));
    await waitFor(() =>
      expect(contentRequestAction).toHaveBeenCalledWith(
        3,
        expect.objectContaining({ action: 'approve' })
      )
    );
  });

  it('links catalog id on mark added', async () => {
    getContentRequest.mockResolvedValue({
      request: {
        id: 3,
        request_type: 'movie',
        title: 'Dune Part Three',
        status: 'approved',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      events: [],
    });
    contentRequestAction.mockResolvedValue({
      id: 3,
      request_type: 'movie',
      title: 'Dune Part Three',
      status: 'added',
      linked_movie_id: 42,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    render(
      <MemoryRouter>
        <ContentRequestsAdminPage />
      </MemoryRouter>
    );
    fireEvent.click(await screen.findByTestId('cr-row-3'));
    await waitFor(() => expect(screen.getByTestId('cr-link-id')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('cr-link-id'), { target: { value: '42' } });
    fireEvent.click(screen.getByTestId('cr-action-mark-added'));
    await waitFor(() =>
      expect(contentRequestAction).toHaveBeenCalledWith(
        3,
        expect.objectContaining({ action: 'mark_added', linked_movie_id: 42 })
      )
    );
  });
});
