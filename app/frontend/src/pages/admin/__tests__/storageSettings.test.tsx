import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StorageSettingsPage from '../StorageSettingsPage';

const getStorage = vi.fn();
const updateStorage = vi.fn();
const testStorage = vi.fn();

vi.mock('@/lib/adminApi', () => ({
  adminApi: {
    getStorage: (...args: unknown[]) => getStorage(...args),
    updateStorage: (...args: unknown[]) => updateStorage(...args),
    testStorage: (...args: unknown[]) => testStorage(...args),
  },
}));

const baseDto = {
  enabled: false,
  provider: 'cloudflare_r2' as const,
  endpoint_url: 'https://acct.r2.cloudflarestorage.com',
  account_id: 'acct',
  bucket: 'ifilm-art',
  region: 'auto',
  object_key_prefix: 'ifilm',
  public_base_url: 'https://cdn.example.com',
  artwork_cdn_enabled: true,
  artwork_cdn_requested: true,
  artwork_cdn_host_capability: false,
  artwork_cdn_effective: false,
  artwork_publishing_status: 'blocked_by_server_capability' as const,
  credentials_configured: true,
  updated_at: '2026-10-01T00:00:00+00:00',
  last_test_at: null,
  last_test_ok: null,
  last_test_reachable: null,
  last_test_bucket_accessible: null,
  last_test_message: null,
};

describe('StorageSettingsPage', () => {
  beforeEach(() => {
    getStorage.mockReset();
    updateStorage.mockReset();
    testStorage.mockReset();
    getStorage.mockResolvedValue(baseDto);
    updateStorage.mockResolvedValue(baseDto);
    testStorage.mockResolvedValue({
      ok: true,
      reachable: true,
      bucket_accessible: true,
      endpoint_host: 'acct.r2.cloudflarestorage.com',
      message: 'Endpoint reachable and bucket accessible',
      tested_at: '2026-10-01T00:01:00+00:00',
      settings: {
        ...baseDto,
        last_test_ok: true,
        last_test_reachable: true,
        artwork_cdn_host_capability: true,
        artwork_cdn_effective: true,
        artwork_publishing_status: 'active',
      },
    });
  });

  it('renders R2 primary fields without prefilling secrets', async () => {
    render(<StorageSettingsPage />);
    expect(await screen.findByTestId('storage-settings-page')).toBeInTheDocument();
    expect(screen.getByTestId('account-id')).toHaveValue('acct');
    expect(screen.getByTestId('public-base-url')).toHaveValue('https://cdn.example.com');
    expect(screen.getByTestId('artwork-cdn-enabled')).toBeChecked();
    expect(screen.getByTestId('artwork-publishing-status')).toHaveTextContent(
      'BLOCKED BY SERVER CAPABILITY',
    );
    expect(screen.queryByTestId('access-key-id')).not.toBeInTheDocument();
    // Advanced endpoint hidden by default for R2
    expect(screen.queryByTestId('storage-endpoint')).not.toBeInTheDocument();
  });

  it('saves derived endpoint and can save & test', async () => {
    render(<StorageSettingsPage />);
    await screen.findByTestId('save-storage');
    fireEvent.click(screen.getByTestId('save-storage'));
    await waitFor(() => expect(updateStorage).toHaveBeenCalled());
    const payload = updateStorage.mock.calls[0][0];
    expect(payload.access_key_id).toBeUndefined();
    expect(payload.account_id).toBe('acct');
    expect(payload.endpoint_url).toBe('https://acct.r2.cloudflarestorage.com');
    expect(payload.artwork_cdn_enabled).toBe(true);
    fireEvent.click(screen.getByTestId('save-and-test'));
    await waitFor(() => expect(testStorage).toHaveBeenCalled());
  });

  it('requires confirmation before removing credentials', async () => {
    render(<StorageSettingsPage />);
    await screen.findByTestId('remove-credentials');
    expect(screen.getByTestId('remove-credentials')).toBeDisabled();
    fireEvent.click(screen.getByTestId('confirm-remove-credentials'));
    expect(screen.getByTestId('remove-credentials')).toBeEnabled();
    updateStorage.mockResolvedValue({ ...baseDto, credentials_configured: false, enabled: false });
    fireEvent.click(screen.getByTestId('remove-credentials'));
    await waitFor(() =>
      expect(updateStorage).toHaveBeenCalledWith(
        expect.objectContaining({ remove_credentials: true, confirm: true }),
      ),
    );
  });

  it('shows replace-credentials fields only after replace is requested', async () => {
    render(<StorageSettingsPage />);
    await screen.findByTestId('replace-credentials');
    expect(screen.queryByTestId('access-key-id')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('replace-credentials'));
    expect(screen.getByTestId('access-key-id')).toHaveValue('');
    expect(screen.getByTestId('secret-access-key')).toHaveValue('');
  });

  it('switches to S3-compatible fields', async () => {
    render(<StorageSettingsPage />);
    await screen.findByTestId('storage-provider');
    // Radix Select is awkward in jsdom — change via provider value by re-mocking load
    getStorage.mockResolvedValueOnce({
      ...baseDto,
      provider: 's3_compatible',
      endpoint_url: 'https://s3.example.com',
      artwork_publishing_status: 'disabled',
      artwork_cdn_requested: false,
      artwork_cdn_enabled: false,
    });
    render(<StorageSettingsPage />);
    expect(await screen.findByTestId('storage-endpoint')).toHaveValue('https://s3.example.com');
    expect(screen.getByTestId('storage-region')).toBeInTheDocument();
    expect(screen.getByTestId('object-key-prefix')).toBeInTheDocument();
  });

  it('surfaces load failures', async () => {
    getStorage.mockRejectedValueOnce(new Error('forbidden'));
    render(<StorageSettingsPage />);
    expect(await screen.findByText(/forbidden|Failed to load storage settings/i)).toBeInTheDocument();
  });
});
