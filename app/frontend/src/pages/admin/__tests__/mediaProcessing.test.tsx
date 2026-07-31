import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MediaAssetDetailPage from '../MediaAssetDetailPage';
import MediaProcessingJobsPage from '../MediaProcessingJobsPage';
import { ApiError, tokenStore } from '@/lib/api';
import { LangProvider } from '@/components/CustomerLayout';

const getMediaAsset = vi.fn();
const listAssetProcessingJobs = vi.fn();
const listAssetPackages = vi.fn();
const getProcessingStatus = vi.fn();
const queueMediaProbe = vi.fn();
const queueMediaEncodeHls = vi.fn();
const retryProcessingJob = vi.fn();
const cancelProcessingJob = vi.fn();
const listProcessingJobs = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      getMediaAsset: (...args: unknown[]) => getMediaAsset(...args),
      listAssetProcessingJobs: (...args: unknown[]) => listAssetProcessingJobs(...args),
      listAssetPackages: (...args: unknown[]) => listAssetPackages(...args),
      getProcessingStatus: (...args: unknown[]) => getProcessingStatus(...args),
      queueMediaProbe: (...args: unknown[]) => queueMediaProbe(...args),
      queueMediaEncodeHls: (...args: unknown[]) => queueMediaEncodeHls(...args),
      retryProcessingJob: (...args: unknown[]) => retryProcessingJob(...args),
      cancelProcessingJob: (...args: unknown[]) => cancelProcessingJob(...args),
      listProcessingJobs: (...args: unknown[]) => listProcessingJobs(...args),
    },
  };
});

function wrap(ui: React.ReactNode, initial: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LangProvider>
        <MemoryRouter initialEntries={[initial]}>{ui}</MemoryRouter>
      </LangProvider>
    </QueryClientProvider>
  );
}

const asset = {
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
  width: 64,
  height: 64,
  duration_seconds: 1,
  storage_backend: 'local',
  storage_path: 'originals/asset-1/asset-1.mp4',
  category: 'originals',
  upload_status: 'completed',
  processing_status: 'none',
  container_format: null,
  video_codec: null,
  audio_codec: null,
  audio_stream_count: null,
  subtitle_stream_count: null,
  probed_at: null,
  created_by_admin_id: 1,
};

describe('media processing admin UI', () => {
  beforeEach(() => {
    tokenStore.setAdmin('tok');
    getMediaAsset.mockResolvedValue(asset);
    listAssetProcessingJobs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1 });
    listAssetPackages.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1 });
    getProcessingStatus.mockResolvedValue({
      enabled: true,
      ffmpeg_available: true,
      ffprobe_available: true,
    });
    listProcessingJobs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    queueMediaProbe.mockResolvedValue({
      created: true,
      job: {
        id: 'job-1',
        media_asset_id: 'asset-1',
        job_type: 'probe',
        status: 'queued',
        priority: 100,
        attempt_count: 0,
        max_attempts: 3,
        progress_percent: 0,
        current_step: 'queued',
        error_code: null,
        error_message: null,
        worker_id: null,
        cancel_requested: false,
        created_by_admin_id: 1,
      },
    });
    queueMediaEncodeHls.mockResolvedValue({
      created: true,
      job: {
        id: 'job-enc-1',
        media_asset_id: 'asset-1',
        job_type: 'encode_hls',
        status: 'queued',
        priority: 200,
        attempt_count: 0,
        max_attempts: 3,
        progress_percent: 0,
        current_step: 'queued',
        error_code: null,
        error_message: null,
        worker_id: null,
        cancel_requested: false,
        created_by_admin_id: 1,
      },
      package: {
        id: 'pkg-1',
        media_asset_id: 'asset-1',
        processing_job_id: 'job-enc-1',
        package_type: 'hls_vod',
        status: 'pending',
        storage_path: null,
        master_playlist_path: null,
        source_width: 640,
        source_height: 360,
        duration_seconds: 1,
        segment_duration_seconds: 6,
        rendition_count: 0,
        error_code: null,
        error_message: null,
        created_by_admin_id: 1,
        renditions: [],
      },
    });
    retryProcessingJob.mockResolvedValue({ id: 'job-1', status: 'queued' });
    cancelProcessingJob.mockResolvedValue({ id: 'job-1', status: 'cancelled' });
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    tokenStore.clearAdmin();
  });

  it('renders processing status and queues a probe', async () => {
    wrap(
      <Routes>
        <Route path="/admin/media/:assetId" element={<MediaAssetDetailPage />} />
      </Routes>,
      '/admin/media/asset-1'
    );
    await waitFor(() => expect(screen.getByTestId('processing-panel')).toBeInTheDocument());
    expect(screen.getByTestId('processing-status')).toHaveTextContent('none');
    fireEvent.click(screen.getByTestId('probe-media'));
    await waitFor(() => expect(queueMediaProbe).toHaveBeenCalledWith('asset-1'));
  });

  it('shows feature-disabled state', async () => {
    getProcessingStatus.mockResolvedValue({
      enabled: false,
      ffmpeg_available: false,
      ffprobe_available: false,
    });
    wrap(
      <Routes>
        <Route path="/admin/media/:assetId" element={<MediaAssetDetailPage />} />
      </Routes>,
      '/admin/media/asset-1'
    );
    await waitFor(() => expect(screen.getByTestId('processing-disabled')).toBeInTheDocument());
  });

  it('retries and cancels jobs', async () => {
    listAssetProcessingJobs.mockResolvedValue({
      items: [
        {
          id: 'job-1',
          media_asset_id: 'asset-1',
          job_type: 'probe',
          status: 'failed',
          priority: 100,
          attempt_count: 1,
          max_attempts: 3,
          progress_percent: 50,
          current_step: 'failed',
          error_code: 'probe_failed',
          error_message: 'bad file',
          worker_id: null,
          cancel_requested: false,
          created_by_admin_id: 1,
        },
      ],
      total: 1,
      page: 1,
      page_size: 1,
    });
    wrap(
      <Routes>
        <Route path="/admin/media/:assetId" element={<MediaAssetDetailPage />} />
      </Routes>,
      '/admin/media/asset-1'
    );
    await waitFor(() => expect(screen.getByTestId('retry-probe')).toBeInTheDocument());
    expect(screen.getByTestId('job-error')).toHaveTextContent(/bad file/i);
    fireEvent.click(screen.getByTestId('retry-probe'));
    await waitFor(() => expect(retryProcessingJob).toHaveBeenCalledWith('job-1'));

    listAssetProcessingJobs.mockResolvedValue({
      items: [
        {
          id: 'job-2',
          media_asset_id: 'asset-1',
          job_type: 'probe',
          status: 'running',
          priority: 100,
          attempt_count: 1,
          max_attempts: 3,
          progress_percent: 50,
          current_step: 'running_ffprobe',
          error_code: null,
          error_message: null,
          worker_id: 'w1',
          cancel_requested: false,
          created_by_admin_id: 1,
        },
      ],
      total: 1,
      page: 1,
      page_size: 1,
    });
    fireEvent.click(screen.getByTestId('probe-media'));
    await waitFor(() => expect(screen.getByTestId('cancel-probe')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('cancel-probe'));
    await waitFor(() => expect(cancelProcessingJob).toHaveBeenCalled());
  });

  it('stops polling when job is terminal', async () => {
    const spy = listAssetProcessingJobs;
    spy.mockResolvedValue({
      items: [
        {
          id: 'job-1',
          media_asset_id: 'asset-1',
          job_type: 'probe',
          status: 'completed',
          priority: 100,
          attempt_count: 1,
          max_attempts: 3,
          progress_percent: 100,
          current_step: 'completed',
          error_code: null,
          error_message: null,
          worker_id: 'w1',
          cancel_requested: false,
          created_by_admin_id: 1,
        },
      ],
      total: 1,
      page: 1,
      page_size: 1,
    });
    wrap(
      <Routes>
        <Route path="/admin/media/:assetId" element={<MediaAssetDetailPage />} />
      </Routes>,
      '/admin/media/asset-1'
    );
    await waitFor(() => expect(spy).toHaveBeenCalled());
    const calls = spy.mock.calls.length;
    await vi.advanceTimersByTimeAsync(10000);
    expect(spy.mock.calls.length).toBe(calls);
  });

  it('renders processing jobs page empty and error states', async () => {
    wrap(
      <Routes>
        <Route path="/admin/media/processing" element={<MediaProcessingJobsPage />} />
      </Routes>,
      '/admin/media/processing'
    );
    await waitFor(() => expect(screen.getByTestId('processing-jobs-page')).toBeInTheDocument());
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();

    listProcessingJobs.mockRejectedValue(new ApiError('boom', 500));
    fireEvent.click(screen.getByText('Refresh'));
    await waitFor(() => expect(screen.getByTestId('error-state')).toBeInTheDocument());
  });

  it('queues HLS encode when probe metadata is present', async () => {
    getMediaAsset.mockResolvedValue({
      ...asset,
      width: 640,
      height: 360,
      probed_at: '2026-07-31T00:00:00Z',
      processing_status: 'completed',
    });
    wrap(
      <Routes>
        <Route path="/admin/media/:assetId" element={<MediaAssetDetailPage />} />
      </Routes>,
      '/admin/media/asset-1'
    );
    await waitFor(() => expect(screen.getByTestId('encode-hls')).toBeInTheDocument());
    expect(screen.getByTestId('encode-hls')).not.toBeDisabled();
    fireEvent.click(screen.getByTestId('encode-hls'));
    await waitFor(() => expect(queueMediaEncodeHls).toHaveBeenCalledWith('asset-1'));
    expect(screen.getByTestId('packages-panel')).toBeInTheDocument();
  });
});
