import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { LangProvider } from '@/components/CustomerLayout';
import CollectionsListPage from '../CollectionsListPage';
import CollectionFormPage, { collectionFormSchema } from '../CollectionFormPage';
import { ApiError } from '@/lib/api';

const listCollections = vi.fn();
const getCollection = vi.fn();
const createCollection = vi.fn();
const updateCollection = vi.fn();
const publishCollection = vi.fn();
const collectionPicker = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      listCollections: (...args: unknown[]) => listCollections(...args),
      getCollection: (...args: unknown[]) => getCollection(...args),
      createCollection: (...args: unknown[]) => createCollection(...args),
      updateCollection: (...args: unknown[]) => updateCollection(...args),
      publishCollection: (...args: unknown[]) => publishCollection(...args),
      unpublishCollection: vi.fn(),
      archiveCollection: vi.fn(),
      deleteCollection: vi.fn(),
      previewCollection: vi.fn().mockResolvedValue({
        id: 1,
        title: 'Preview',
        slug: 'preview',
        collection_type: 'editorial',
        items: [],
      }),
      collectionPicker: (...args: unknown[]) => collectionPicker(...args),
    },
  };
});

function wrap(_ui: React.ReactNode, initial: string) {
  const router = createMemoryRouter(
    [
      { path: '/admin/collections', element: <CollectionsListPage /> },
      { path: '/admin/collections/new', element: <CollectionFormPage /> },
      { path: '/admin/collections/:id/edit', element: <CollectionFormPage /> },
    ],
    { initialEntries: [initial] }
  );
  return render(
    <LangProvider>
      <RouterProvider router={router} />
    </LangProvider>
  );
}

describe('admin collections pages', () => {
  beforeEach(() => {
    listCollections.mockReset();
    getCollection.mockReset();
    createCollection.mockReset();
    updateCollection.mockReset();
    publishCollection.mockReset();
    collectionPicker.mockReset();
    collectionPicker.mockResolvedValue({ movies: [], series: [], page: 1, page_size: 20 });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders the collections list with status/type and search controls', async () => {
    listCollections.mockResolvedValue({
      items: [
        {
          id: 5,
          title: 'Staff Picks',
          slug: 'staff-picks',
          collection_type: 'staff_pick',
          status: 'draft',
          visibility: 'public',
          item_count: 3,
          items: [],
          is_featured: false,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    wrap(<CollectionsListPage />, '/admin/collections');

    await waitFor(() => {
      expect(screen.getAllByText('Staff Picks').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getByTestId('collections-search')).toBeInTheDocument();
    expect(screen.getByTestId('collections-status-filter')).toBeInTheDocument();
    expect(screen.getByTestId('collections-type-filter')).toBeInTheDocument();
    expect(listCollections).toHaveBeenCalled();
  });

  it('shows an empty state with a New Collection action when there are no collections', async () => {
    listCollections.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });

    wrap(<CollectionsListPage />, '/admin/collections');

    await waitFor(() => expect(screen.getByTestId('empty-state')).toBeInTheDocument());
    expect(screen.getAllByRole('link', { name: /new collection/i }).length).toBeGreaterThanOrEqual(1);
  });

  it('shows an error state with retry when the list fails to load', async () => {
    listCollections.mockRejectedValue(new ApiError('Server exploded', 500));

    wrap(<CollectionsListPage />, '/admin/collections');

    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toHaveTextContent(/server exploded/i);
    });
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('validates collection form title is required', () => {
    const result = collectionFormSchema.safeParse({
      title: '',
      collection_type: 'editorial',
      visibility: 'public',
      is_featured: false,
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.title?.[0]).toMatch(/required/i);
    }
  });

  it('validates artwork URLs must start with http/https', () => {
    const result = collectionFormSchema.safeParse({
      title: 'Valid title',
      collection_type: 'editorial',
      visibility: 'public',
      is_featured: false,
      poster_url: 'not-a-url',
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.flatten().fieldErrors.poster_url?.[0]).toMatch(/http/i);
    }
  });

  it('creates a new collection and navigates to the edit route', async () => {
    createCollection.mockResolvedValue({
      id: 42,
      title: 'New Collection',
      slug: 'new-collection',
      collection_type: 'editorial',
      status: 'draft',
      visibility: 'public',
      items: [],
    });
    getCollection.mockResolvedValue({
      id: 42,
      title: 'New Collection',
      slug: 'new-collection',
      collection_type: 'editorial',
      status: 'draft',
      visibility: 'public',
      items: [],
    });

    wrap(<CollectionFormPage />, '/admin/collections/new');

    await waitFor(() => expect(screen.getByTestId('collection-title')).toBeInTheDocument());
    fireEvent.change(screen.getByTestId('collection-title'), { target: { value: 'New Collection' } });
    fireEvent.click(screen.getByTestId('collection-save'));

    await waitFor(() => {
      expect(createCollection).toHaveBeenCalled();
    });
    expect(createCollection.mock.calls[0][0].title).toBe('New Collection');
  });

  it('renders Items and Publishing tabs with reorder controls when editing', async () => {
    getCollection.mockResolvedValue({
      id: 7,
      title: 'Editorial Picks',
      slug: 'editorial-picks',
      collection_type: 'editorial',
      status: 'draft',
      visibility: 'public',
      updated_at: '2024-01-01T00:00:00Z',
      item_count: 2,
      items: [
        {
          id: 1,
          collection_id: 7,
          movie_id: 10,
          position: 0,
          content_type: 'movie',
          movie: { id: 10, title: 'Alpha', slug: 'alpha', status: 'published' },
        },
        {
          id: 2,
          collection_id: 7,
          movie_id: 11,
          position: 1,
          content_type: 'movie',
          movie: { id: 11, title: 'Beta', slug: 'beta', status: 'published' },
        },
      ],
    });

    wrap(<CollectionFormPage />, '/admin/collections/7/edit');

    await waitFor(() => expect(screen.getByTestId('collection-form-page')).toBeInTheDocument());
    // Radix TabsTrigger activates on mousedown (automatic activation mode), not click.
    fireEvent.mouseDown(screen.getByRole('tab', { name: /items/i }));

    await waitFor(() => expect(screen.getByTestId('collection-items-list')).toBeInTheDocument());
    expect(screen.getByTestId('collection-item-up-1')).toBeDisabled();
    expect(screen.getByTestId('collection-item-down-2')).toBeDisabled();
    expect(screen.getByTestId('collection-item-down-1')).not.toBeDisabled();

    fireEvent.mouseDown(screen.getByRole('tab', { name: /publishing/i }));
    await waitFor(() => expect(screen.getByTestId('collection-publish')).toBeInTheDocument());
  });
});
