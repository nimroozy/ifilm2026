import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import RequestContentPage from '@/pages/RequestContentPage';
import { LangProvider } from '@/components/CustomerLayout';

const createContentRequest = vi.fn();
const listContentRequests = vi.fn();
const search = vi.fn();
const withdrawContentRequest = vi.fn();

vi.mock('@/lib/api', () => ({
  api: {
    createContentRequest: (...args: unknown[]) => createContentRequest(...args),
    listContentRequests: (...args: unknown[]) => listContentRequests(...args),
    search: (...args: unknown[]) => search(...args),
    withdrawContentRequest: (...args: unknown[]) => withdrawContentRequest(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status = 400) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock('@/components/CustomerLayout', async () => {
  const actual = await vi.importActual<typeof import('@/components/CustomerLayout')>(
    '@/components/CustomerLayout'
  );
  return {
    ...actual,
    useAuth: () => ({ isLoggedIn: true }),
  };
});

function wrap(ui: React.ReactNode) {
  return (
    <MemoryRouter>
      <LangProvider>{ui}</LangProvider>
    </MemoryRouter>
  );
}

describe('RequestContentPage', () => {
  beforeEach(() => {
    createContentRequest.mockReset();
    listContentRequests.mockReset();
    search.mockReset();
    withdrawContentRequest.mockReset();
    listContentRequests.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    search.mockResolvedValue({ movies: [], series: [] });
  });

  it('renders form, disclaimer, and my requests', async () => {
    render(wrap(<RequestContentPage />));
    expect(screen.getByTestId('request-content-page')).toBeInTheDocument();
    expect(screen.getByTestId('request-disclaimer')).toHaveTextContent(/does not guarantee/i);
    expect(screen.getByTestId('request-form')).toBeInTheDocument();
    expect(screen.getByTestId('my-requests')).toBeInTheDocument();
    await waitFor(() => expect(listContentRequests).toHaveBeenCalled());
  });

  it('submits a movie request', async () => {
    const user = userEvent.setup();
    createContentRequest.mockResolvedValue({
      outcome: 'created',
      message: 'ok',
      request: {
        id: 9,
        request_type: 'movie',
        title: 'Dune Part Three',
        status: 'new',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      suggestions: [],
    });
    listContentRequests
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 50 })
      .mockResolvedValueOnce({
        items: [
          {
            id: 9,
            request_type: 'movie',
            title: 'Dune Part Three',
            status: 'new',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
      });

    render(wrap(<RequestContentPage />));
    await user.type(screen.getByTestId('request-title'), 'Dune Part Three');
    await user.click(screen.getByTestId('request-submit'));
    await waitFor(() => expect(createContentRequest).toHaveBeenCalled());
    expect(createContentRequest.mock.calls[0][0]).toMatchObject({
      request_type: 'movie',
      title: 'Dune Part Three',
    });
    await waitFor(() => expect(screen.getByTestId('my-request-9')).toBeInTheDocument());
  });

  it('shows already-available catalog match', async () => {
    const user = userEvent.setup();
    createContentRequest.mockResolvedValue({
      outcome: 'already_available',
      message: 'This title is already available.',
      catalog_item: {
        content_type: 'movie',
        id: 1,
        slug: 'inception',
        title: 'Inception',
        release_year: 2010,
        detail_path: '/movie/inception',
      },
      suggestions: [],
    });
    render(wrap(<RequestContentPage />));
    await user.type(screen.getByTestId('request-title'), 'Inception');
    await user.click(screen.getByTestId('request-submit'));
    await waitFor(() => expect(screen.getByTestId('catalog-match')).toBeInTheDocument());
    expect(screen.getByTestId('request-form-message')).toHaveTextContent(/already available/i);
  });

  it('toggles series type', async () => {
    const user = userEvent.setup();
    render(wrap(<RequestContentPage />));
    await user.click(screen.getByTestId('request-type-series'));
    expect(screen.getByTestId('request-type-series')).toHaveAttribute('aria-pressed', 'true');
  });
});
