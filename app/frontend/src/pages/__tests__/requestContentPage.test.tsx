import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import RequestContentPage from '@/pages/RequestContentPage';

const createContentRequest = vi.fn();
const listContentRequests = vi.fn();
const search = vi.fn();
const withdrawContentRequest = vi.fn();

const requestContent = {
  title: 'Request Movie',
  subtitle: 'Ask the iFilm team to review a movie or series.',
  disclaimer:
    'Requests are reviewed by the iFilm team. Submitting a request does not guarantee that the title will be added.',
  typeLabel: 'Type',
  movie: 'Movie',
  series: 'Series',
  titleLabel: 'Title',
  yearLabel: 'Year (optional)',
  tmdbLabel: 'TMDB link (optional)',
  imdbLabel: 'IMDb link (optional)',
  languageLabel: 'Preferred language (optional)',
  notesLabel: 'Notes (optional)',
  submit: 'Submit request',
  submitting: 'Submitting…',
  signInPrompt: 'Sign in',
  signIn: 'Sign In',
  myRequests: 'My Requests',
  emptyRequests: 'You have not submitted any requests yet.',
  status: 'Status',
  requested: 'Requested',
  preferredLanguage: 'Preferred language',
  response: 'Response',
  availableNow: 'Available now',
  viewTitle: 'View',
  withdraw: 'Withdraw',
  alreadyAvailable: 'This title is already available.',
  existingRequest: 'You already have an open request for this title.',
  suggestionsTitle: 'Similar titles may already be available',
  continueAnyway: 'Continue with my request',
  catalogHint: 'Already available in the catalog',
  success: 'Request submitted for review.',
  errorGeneric: 'Unable to submit request',
  rateLimited: 'Too many requests. Please try again later.',
  statuses: {
    new: 'New',
    reviewing: 'Reviewing',
    approved: 'Approved',
    rejected: 'Rejected',
    added: 'Added',
    withdrawn: 'Withdrawn',
  },
};

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

vi.mock('@/components/CustomerLayout', () => ({
  useLang: () => ({ t: { requestContent }, lang: 'en', dir: 'ltr' }),
  useAuth: () => ({ isLoggedIn: true }),
}));

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
    render(
      <MemoryRouter>
        <RequestContentPage />
      </MemoryRouter>
    );
    expect(screen.getByTestId('request-content-page')).toBeInTheDocument();
    expect(screen.getByTestId('request-disclaimer')).toHaveTextContent(/does not guarantee/i);
    expect(screen.getByTestId('request-form')).toBeInTheDocument();
    expect(screen.getByTestId('my-requests')).toBeInTheDocument();
    await waitFor(() => expect(listContentRequests).toHaveBeenCalled());
  });

  it('submits a movie request', async () => {
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

    render(
      <MemoryRouter>
        <RequestContentPage />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByTestId('request-title'), { target: { value: 'Dune Part Three' } });
    fireEvent.click(screen.getByTestId('request-submit'));
    await waitFor(() => expect(createContentRequest).toHaveBeenCalled());
    expect(createContentRequest.mock.calls[0][0]).toMatchObject({
      request_type: 'movie',
      title: 'Dune Part Three',
    });
    await waitFor(() => expect(screen.getByTestId('my-request-9')).toBeInTheDocument());
    expect(screen.getByTestId('my-request-9')).toHaveTextContent('New');
  });

  it('shows already-available catalog match', async () => {
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
    render(
      <MemoryRouter>
        <RequestContentPage />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByTestId('request-title'), { target: { value: 'Inception' } });
    fireEvent.click(screen.getByTestId('request-submit'));
    await waitFor(() => expect(screen.getByTestId('catalog-match')).toBeInTheDocument());
    expect(screen.getByTestId('request-form-message')).toHaveTextContent(/already available/i);
  });

  it('toggles series type', () => {
    render(
      <MemoryRouter>
        <RequestContentPage />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByTestId('request-type-series'));
    expect(screen.getByTestId('request-type-series')).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows Added link when request is fulfilled', async () => {
    listContentRequests.mockResolvedValue({
      items: [
        {
          id: 4,
          request_type: 'movie',
          title: 'Arrival',
          status: 'added',
          linked_detail_path: '/movie/arrival',
          linked_title: 'Arrival',
          public_response: 'Available now',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
    });
    render(
      <MemoryRouter>
        <RequestContentPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByTestId('my-request-link-4')).toBeInTheDocument());
    expect(screen.getByTestId('my-request-link-4')).toHaveAttribute('href', '/movie/arrival');
  });
});
