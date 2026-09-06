import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import StorageSettingsPage from '../StorageSettingsPage';

const getStorage = vi.fn();
const updateStorage = vi.fn();
const testStorage = vi.fn();

vi.mock('@/lib/cdnApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/cdnApi')>('@/lib/cdnApi');
  return {
    ...actual,
    cdnApi: {
      ...actual.cdnApi,
      getStorage: (...args: unknown[]) => getStorage(...args),
      updateStorage: (...args: unknown[]) => updateStorage(...args),
      testStorage: (...args: unknown[]) => testStorage(...args),
    },
  };
});

const baseDto = {
  enabled: false,
  provider: 'cloudflare_r2' as const,
  endpoint_url: 'https://acct.r2.cloudflarestorage.com',
  account_id: 'acct',
  bucket: 'ifilm-hot',
  region: 'auto',
  object_key_prefix: 'ifilm',
  credentials_configured: true,
  updated_at: '2026-09-01T10:00:00Z',
  last_test_at: null,
  last_test_ok: null,
  last_test_reachable: null,
  last_test_bucket_accessible: null,
  last_test_message: null,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <StorageSettingsPage />
    </MemoryRouter>
  );
}

describe('StorageSettingsPage', () => {
  beforeEach(() => {
    getStorage.mockReset();
    updateStorage.mockReset();
    testStorage.mockReset();
  });

  it('never renders secrets and preserves them when saving without new keys', async () => {
    getStorage.mockResolvedValue(baseDto);
    updateStorage.mockResolvedValue({ ...baseDto, bucket: 'ifilm-hot-2' });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('storage-settings-page')).toBeInTheDocument());
    expect(screen.getByTestId('storage-secret-status').textContent).toBe('Configured');
    expect(screen.getByTestId('storage-replace-secret')).toBeInTheDocument();
    expect(screen.queryByTestId('storage-secret-key')).toBeNull();
    fireEvent.change(screen.getByTestId('storage-bucket'), { target: { value: 'ifilm-hot-2' } });
    fireEvent.click(screen.getByTestId('storage-save'));
    await waitFor(() => expect(updateStorage).toHaveBeenCalledTimes(1));
    const payload = updateStorage.mock.calls[0][0];
    expect(payload.bucket).toBe('ifilm-hot-2');
    expect(payload).not.toHaveProperty('secret_access_key');
    expect(payload).not.toHaveProperty('access_key_id');
  });

  it('replace secret sends both keys and test connection shows status', async () => {
    getStorage.mockResolvedValue(baseDto);
    updateStorage.mockResolvedValue(baseDto);
    testStorage.mockResolvedValue({
      ok: false,
      reachable: true,
      bucket_accessible: false,
      endpoint_host: 'acct.r2.cloudflarestorage.com',
      message: 'Bucket was not found on this endpoint',
      tested_at: '2026-09-06T12:00:00Z',
      settings: { ...baseDto, last_test_at: '2026-09-06T12:00:00Z', last_test_ok: false, last_test_reachable: true, last_test_bucket_accessible: false, last_test_message: 'Bucket was not found on this endpoint' },
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('storage-replace-secret')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('storage-replace-secret'));
    fireEvent.change(screen.getByTestId('storage-access-key'), { target: { value: 'new-access' } });
    expect((screen.getByTestId('storage-save') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId('storage-secret-key'), { target: { value: 'new-secret' } });
    fireEvent.click(screen.getByTestId('storage-save'));
    await waitFor(() => expect(updateStorage).toHaveBeenCalledTimes(1));
    expect(updateStorage.mock.calls[0][0]).toMatchObject({ access_key_id: 'new-access', secret_access_key: 'new-secret' });
    fireEvent.click(screen.getByTestId('storage-test'));
    await waitFor(() => expect(testStorage).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('storage-last-result').textContent).toContain('Fail'));
    expect(screen.getByTestId('storage-status-card').textContent).toContain('Bucket was not found');
    expect(document.body.textContent).not.toContain('new-secret');
  });

  it('blocks enabling without credentials', async () => {
    getStorage.mockResolvedValue({ ...baseDto, credentials_configured: false });
    renderPage();
    await waitFor(() => expect(screen.getByTestId('storage-enabled-switch')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('storage-enabled-switch'));
    await waitFor(() => expect(screen.getByText('Credentials required')).toBeInTheDocument());
    expect((screen.getByTestId('storage-save') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('storage-test') as HTMLButtonElement).disabled).toBe(true);
  });
});
