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
      settings: { ...baseDto, last_test_ok: true, last_test_reachable: true },
    });
  });

  it('renders storage fields without prefilling secrets', async () => {
    render(<StorageSettingsPage />);
    expect(await screen.findByTestId('storage-settings-page')).toBeInTheDocument();
    expect(screen.getByTestId('storage-endpoint')).toHaveValue(
      'https://acct.r2.cloudflarestorage.com',
    );
    expect(screen.getByTestId('public-base-url')).toHaveValue('https://cdn.example.com');
    expect(screen.getByTestId('artwork-cdn-enabled')).toBeChecked();
    expect(screen.getByText('Credentials configured: Yes')).toBeInTheDocument();
    expect(screen.queryByTestId('access-key-id')).not.toBeInTheDocument();
  });

  it('saves settings and can test connection', async () => {
    render(<StorageSettingsPage />);
    await screen.findByTestId('save-storage');
    fireEvent.click(screen.getByTestId('save-storage'));
    await waitFor(() => expect(updateStorage).toHaveBeenCalled());
    const payload = updateStorage.mock.calls[0][0];
    expect(payload.access_key_id).toBeUndefined();
    expect(payload.artwork_cdn_enabled).toBe(true);
    fireEvent.click(screen.getByTestId('test-connection'));
    await waitFor(() => expect(testStorage).toHaveBeenCalled());
    expect(await screen.findByText('Endpoint reachable: Yes')).toBeInTheDocument();
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

  it('surfaces load failures', async () => {
    getStorage.mockRejectedValueOnce(new Error('forbidden'));
    render(<StorageSettingsPage />);
    expect(await screen.findByText(/forbidden|Failed to load storage settings/i)).toBeInTheDocument();
  });
});
