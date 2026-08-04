import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import MediaLinkingCard from '../MediaLinkingCard';
import MediaUploadPage from '../MediaUploadPage';
import { adminApi } from '@/lib/api';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      listMediaAssets: vi.fn(),
      listAssetPackages: vi.fn(),
      linkMediaAsset: vi.fn(),
      detachMediaAsset: vi.fn(),
      queueMediaProbe: vi.fn(),
      queueMediaEncodeHls: vi.fn(),
      createMediaUploadSession: vi.fn(),
      uploadMediaSessionFile: vi.fn(),
    },
  };
});

const sampleAsset = {
  id: 'asset-1',
  movie_id: 7,
  series_id: null,
  season_id: null,
  episode_id: null,
  original_filename: 'feature.mp4',
  stored_filename: 'feature.mp4',
  mime_type: 'video/mp4',
  extension: '.mp4',
  size_bytes: 2048,
  checksum_sha256: null,
  width: 1920,
  height: 1080,
  duration_seconds: 120,
  storage_backend: 'local',
  storage_path: null,
  category: 'originals',
  upload_status: 'completed',
  processing_status: 'none',
  probed_at: '2026-01-01T00:00:00Z',
  created_by_admin_id: 1,
  created_at: '2026-01-01T00:00:00Z',
};

describe('MediaLinkingCard', () => {
  beforeEach(() => {
    vi.mocked(adminApi.listMediaAssets).mockResolvedValue({
      items: [sampleAsset],
      total: 1,
      page: 1,
      page_size: 50,
    });
    vi.mocked(adminApi.listAssetPackages).mockResolvedValue({
      items: [
        {
          id: 'pkg-1',
          media_asset_id: 'asset-1',
          processing_job_id: null,
          package_type: 'hls_vod',
          status: 'completed',
          is_active: true,
          storage_path: null,
          master_playlist_path: null,
          source_width: 1920,
          source_height: 1080,
          duration_seconds: 120,
          segment_duration_seconds: 6,
          rendition_count: 3,
          renditions: [],
          error_code: null,
          error_message: null,
          created_by_admin_id: 1,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('lists linked assets and upload/link actions', async () => {
    render(
      <MemoryRouter>
        <MediaLinkingCard ownerType="movie" ownerId={7} contentStatus="draft" />
      </MemoryRouter>
    );
    expect(await screen.findByTestId('media-linking-card')).toBeTruthy();
    expect(screen.getByTestId('media-upload-and-link').getAttribute('href')).toBe(
      '/admin/tools/upload?owner_type=movie&owner_id=7'
    );
    expect(screen.getByTestId('media-link-existing')).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText('feature.mp4')).toBeTruthy();
    });
    expect(adminApi.listMediaAssets).toHaveBeenCalledWith(
      expect.objectContaining({ movie_id: 7 })
    );
  });

  it('opens link dialog and lists unassigned assets', async () => {
    vi.mocked(adminApi.listMediaAssets)
      .mockResolvedValueOnce({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
      })
      .mockResolvedValue({
        items: [{ ...sampleAsset, id: 'free-1', movie_id: null, original_filename: 'free.mp4' }],
        total: 1,
        page: 1,
        page_size: 10,
      });

    render(
      <MemoryRouter>
        <MediaLinkingCard ownerType="episode" ownerId={44} contentStatus="draft" />
      </MemoryRouter>
    );
    fireEvent.click(await screen.findByTestId('media-link-existing'));
    expect(await screen.findByTestId('link-existing-media-dialog')).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText('free.mp4')).toBeTruthy();
    });
    expect(adminApi.listMediaAssets).toHaveBeenCalledWith(
      expect.objectContaining({
        unassigned: true,
        video_only: true,
        linkable_only: true,
      })
    );
  });
});

describe('MediaUploadPage owner preselection', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows owner banner and sends movie_id on upload', async () => {
    vi.mocked(adminApi.listMediaAssets).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    });
    vi.mocked(adminApi.createMediaUploadSession).mockResolvedValue({
      session: {
        id: 'sess-1',
        media_asset_id: 'asset-new',
        expected_size_bytes: 10,
        bytes_received: 0,
        status: 'pending',
        progress_percent: 0,
        error: null,
      },
      media_asset: { ...sampleAsset, id: 'asset-new', movie_id: 9 },
    });
    vi.mocked(adminApi.uploadMediaSessionFile).mockResolvedValue({
      id: 'sess-1',
      media_asset_id: 'asset-new',
      expected_size_bytes: 10,
      bytes_received: 10,
      status: 'completed',
      progress_percent: 100,
      error: null,
    });

    render(
      <MemoryRouter initialEntries={['/admin/tools/upload?owner_type=movie&owner_id=9']}>
        <Routes>
          <Route path="/admin/tools/upload" element={<MediaUploadPage />} />
          <Route path="/admin/movies/:id/edit" element={<div>Movie edit</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByTestId('upload-owner-preselect')).toBeTruthy();
    const file = new File([new Uint8Array([0, 1, 2, 3])], 'clip.mp4', { type: 'video/mp4' });
    const input = screen.getByTestId('media-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByTestId('media-upload-submit'));

    await waitFor(() => {
      expect(adminApi.createMediaUploadSession).toHaveBeenCalledWith(
        expect.objectContaining({ movie_id: 9, episode_id: null })
      );
    });
  });
});
