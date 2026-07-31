import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MediaUploadPage from '../MediaUploadPage';
import MediaAssetDetailPage from '../MediaAssetDetailPage';
import { ApiError, tokenStore } from '@/lib/api';
import { LangProvider } from '@/components/CustomerLayout';

const me = vi.fn();
const listMediaAssets = vi.fn();
const createMediaUploadSession = vi.fn();
const uploadMediaSessionFile = vi.fn();
const getMediaAsset = vi.fn();
const listAssetProcessingJobs = vi.fn();
const getProcessingStatus = vi.fn();
const queueMediaProbe = vi.fn();
const retryProcessingJob = vi.fn();
const cancelProcessingJob = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      me: (...args: unknown[]) => me(...args),
      listMediaAssets: (...args: unknown[]) => listMediaAssets(...args),
      createMediaUploadSession: (...args: unknown[]) => createMediaUploadSession(...args),
      uploadMediaSessionFile: (...args: unknown[]) => uploadMediaSessionFile(...args),
      getMediaAsset: (...args: unknown[]) => getMediaAsset(...args),
      listAssetProcessingJobs: (...args: unknown[]) => listAssetProcessingJobs(...args),
      getProcessingStatus: (...args: unknown[]) => getProcessingStatus(...args),
      queueMediaProbe: (...args: unknown[]) => queueMediaProbe(...args),
      retryProcessingJob: (...args: unknown[]) => retryProcessingJob(...args),
      cancelProcessingJob: (...args: unknown[]) => cancelProcessingJob(...args),
    },
  };
});

function wrap(ui: React.ReactNode, initial = '/admin/tools/upload') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LangProvider>
        <MemoryRouter initialEntries={[initial]}>{ui}</MemoryRouter>
      </LangProvider>
    </QueryClientProvider>
  );
}

describe('media upload admin pages', () => {
  beforeEach(() => {
    tokenStore.setAdmin('tok');
    me.mockResolvedValue({
      id: 1,
      username: 'admin',
      email: 'a@b.c',
      full_name: 'Admin',
      is_active: true,
      role_name: 'Super Admin',
      permissions: ['upload'],
    });
    listMediaAssets.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    createMediaUploadSession.mockReset();
    uploadMediaSessionFile.mockReset();
    getMediaAsset.mockReset();
    listAssetProcessingJobs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1 });
    getProcessingStatus.mockResolvedValue({
      enabled: true,
      ffmpeg_available: true,
      ffprobe_available: true,
    });
    queueMediaProbe.mockReset();
    retryProcessingJob.mockReset();
    cancelProcessingJob.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
    tokenStore.clearAdmin();
  });

  it('renders upload page and empty asset list', async () => {
    wrap(
      <Routes>
        <Route path="/admin/tools/upload" element={<MediaUploadPage />} />
      </Routes>
    );
    await waitFor(() => expect(screen.getByTestId('media-upload-page')).toBeInTheDocument());
    expect(screen.getByTestId('empty-state')).toHaveTextContent(/no media assets/i);
  });

  it('shows API error when asset list fails', async () => {
    listMediaAssets.mockRejectedValue(new ApiError('uploads disabled', 503));
    wrap(
      <Routes>
        <Route path="/admin/tools/upload" element={<MediaUploadPage />} />
      </Routes>
    );
    await waitFor(() => expect(screen.getByTestId('error-state')).toHaveTextContent(/uploads disabled/i));
  });

  it('renders media asset details', async () => {
    getMediaAsset.mockResolvedValue({
      id: 'asset-1',
      movie_id: null,
      series_id: null,
      season_id: null,
      episode_id: null,
      original_filename: 'clip.mp4',
      stored_filename: 'asset-1.mp4',
      mime_type: 'video/mp4',
      extension: 'mp4',
      size_bytes: 12,
      checksum_sha256: 'abc',
      width: null,
      height: null,
      duration_seconds: null,
      storage_backend: 'local',
      storage_path: 'originals/asset-1/asset-1.mp4',
      category: 'originals',
      upload_status: 'completed',
      processing_status: 'none',
      created_by_admin_id: 1,
    });
    wrap(
      <Routes>
        <Route path="/admin/media/:assetId" element={<MediaAssetDetailPage />} />
      </Routes>,
      '/admin/media/asset-1'
    );
    await waitFor(() => expect(screen.getByTestId('media-asset-detail')).toBeInTheDocument());
    expect(screen.getByText('clip.mp4')).toBeInTheDocument();
    expect(screen.getByText('abc')).toBeInTheDocument();
  });

  it('starts an upload session for a selected file', async () => {
    createMediaUploadSession.mockResolvedValue({
      session: { id: 'sess-1', media_asset_id: 'asset-1', expected_size_bytes: 4, bytes_received: 0, status: 'pending', progress_percent: 0, error: null },
      media_asset: { id: 'asset-1', original_filename: 'a.mp4' },
    });
    uploadMediaSessionFile.mockResolvedValue({
      id: 'sess-1',
      media_asset_id: 'asset-1',
      expected_size_bytes: 4,
      bytes_received: 4,
      status: 'completed',
      progress_percent: 100,
      error: null,
    });

    wrap(
      <Routes>
        <Route path="/admin/tools/upload" element={<MediaUploadPage />} />
        <Route path="/admin/media/:assetId" element={<div>DETAIL</div>} />
      </Routes>
    );
    await waitFor(() => expect(screen.getByTestId('media-file-input')).toBeInTheDocument());
    const input = screen.getByTestId('media-file-input') as HTMLInputElement;
    const file = new File([new Uint8Array([1, 2, 3, 4])], 'a.mp4', { type: 'video/mp4' });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByTestId('start-upload'));
    await waitFor(() => expect(createMediaUploadSession).toHaveBeenCalled());
    await waitFor(() => expect(uploadMediaSessionFile).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText('DETAIL')).toBeInTheDocument());
  });
});
