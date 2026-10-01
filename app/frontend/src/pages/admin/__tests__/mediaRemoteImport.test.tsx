import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MediaLinkingCard from '../MediaLinkingCard';

const listMediaAssets = vi.fn();
const validateRemoteMediaImport = vi.fn();
const startRemoteMediaImport = vi.fn();
const attachExternalMedia = vi.fn();

vi.mock('@/lib/adminApi', () => ({
  adminApi: {
    listMediaAssets: (...args: unknown[]) => listMediaAssets(...args),
    listMediaPackages: vi.fn().mockResolvedValue([]),
    validateRemoteMediaImport: (...args: unknown[]) => validateRemoteMediaImport(...args),
    startRemoteMediaImport: (...args: unknown[]) => startRemoteMediaImport(...args),
    getRemoteMediaImport: vi.fn(),
    cancelRemoteMediaImport: vi.fn(),
    retryRemoteMediaImport: vi.fn(),
    attachExternalMedia: (...args: unknown[]) => attachExternalMedia(...args),
    queueMediaProbe: vi.fn(),
    queueMediaEncodeHls: vi.fn(),
    detachMediaAsset: vi.fn(),
  },
}));

describe('MediaLinkingCard Add Media', () => {
  beforeEach(() => {
    listMediaAssets.mockReset();
    validateRemoteMediaImport.mockReset();
    startRemoteMediaImport.mockReset();
    attachExternalMedia.mockReset();
    listMediaAssets.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
  });

  it('shows Add Media source choices and import-from-URL flow', async () => {
    validateRemoteMediaImport.mockResolvedValue({
      url_display: 'https://cdn.example.com/movie.mp4?…',
      host: 'cdn.example.com',
      kind: 'mp4',
      content_type: 'video/mp4',
      content_length: 1024,
      accept_ranges: true,
      https_ok: true,
      within_size_limit: true,
      estimated_disk_ok: true,
    });
    startRemoteMediaImport.mockResolvedValue({
      id: 'imp-1',
      job_id: 'job-1',
      media_asset_id: 'asset-1',
      owner_type: 'movie',
      owner_id: 7,
      destination: 'local_origin',
      phase: 'queued',
      status: 'queued',
      source_url_display: 'https://cdn.example.com/movie.mp4?…',
      source_host: 'cdn.example.com',
      accept_ranges: true,
      bytes_downloaded: 0,
      progress_percent: 0,
      retry_count: 0,
      cancel_requested: false,
    });

    render(
      <MemoryRouter>
        <MediaLinkingCard ownerType="movie" ownerId={7} />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('media-add-media')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('media-add-media'));
    expect(await screen.findByTestId('add-media-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('add-media-upload-file')).toBeInTheDocument();
    expect(screen.getByTestId('add-media-import-url')).toBeInTheDocument();
    expect(screen.getByTestId('add-media-external-source')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('add-media-import-url'));
    expect(await screen.findByTestId('import-from-url-dialog')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('remote-import-url-input'), {
      target: { value: 'https://cdn.example.com/movie.mp4?token=SECRET' },
    });
    fireEvent.click(screen.getByTestId('remote-import-validate'));
    await waitFor(() => expect(validateRemoteMediaImport).toHaveBeenCalled());
    expect(await screen.findByTestId('remote-import-validation')).toHaveTextContent('cdn.example.com');
    expect(screen.getByTestId('remote-import-validation').textContent).not.toContain('SECRET');
    fireEvent.click(screen.getByTestId('remote-import-start'));
    await waitFor(() => expect(startRemoteMediaImport).toHaveBeenCalled());
    const payload = startRemoteMediaImport.mock.calls[0][0];
    expect(payload.owner_type).toBe('movie');
    expect(payload.owner_id).toBe(7);
  });

  it('supports episode Import from URL', async () => {
    validateRemoteMediaImport.mockResolvedValue({
      url_display: 'https://cdn.example.com/ep.mp4',
      host: 'cdn.example.com',
      kind: 'mp4',
      content_type: 'video/mp4',
      content_length: 2048,
      accept_ranges: false,
      https_ok: true,
      within_size_limit: true,
      estimated_disk_ok: true,
    });
    startRemoteMediaImport.mockResolvedValue({
      id: 'imp-ep',
      job_id: 'job-ep',
      media_asset_id: 'asset-ep',
      owner_type: 'episode',
      owner_id: 3,
      destination: 'local_origin',
      phase: 'queued',
      status: 'queued',
      source_url_display: 'https://cdn.example.com/ep.mp4',
      source_host: 'cdn.example.com',
      accept_ranges: false,
      bytes_downloaded: 0,
      progress_percent: 0,
      retry_count: 0,
      cancel_requested: false,
    });

    render(
      <MemoryRouter>
        <MediaLinkingCard ownerType="episode" ownerId={3} />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByTestId('media-add-media'));
    fireEvent.click(await screen.findByTestId('add-media-import-url'));
    fireEvent.change(await screen.findByTestId('remote-import-url-input'), {
      target: { value: 'https://cdn.example.com/ep.mp4' },
    });
    fireEvent.click(screen.getByTestId('remote-import-validate'));
    await waitFor(() => expect(validateRemoteMediaImport).toHaveBeenCalled());
    fireEvent.click(await screen.findByTestId('remote-import-start'));
    await waitFor(() => expect(startRemoteMediaImport).toHaveBeenCalled());
    expect(startRemoteMediaImport.mock.calls[0][0].owner_type).toBe('episode');
    expect(startRemoteMediaImport.mock.calls[0][0].owner_id).toBe(3);
  });

  it('requires external acknowledgement warning', async () => {
    render(
      <MemoryRouter>
        <MediaLinkingCard ownerType="episode" ownerId={3} />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByTestId('media-add-media'));
    fireEvent.click(await screen.findByTestId('add-media-external-source'));
    expect(await screen.findByTestId('external-url-dialog')).toBeInTheDocument();
    expect(screen.getByText(/does not use iFilm/i)).toBeInTheDocument();
  });
});
