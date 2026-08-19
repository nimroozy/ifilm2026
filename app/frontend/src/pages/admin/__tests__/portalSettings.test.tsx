import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PortalSettingsPage from '../PortalSettingsPage';
import { tokenStore } from '@/lib/api';
import { LangProvider } from '@/components/CustomerLayout';

const me = vi.fn();
const getPortalIntegration = vi.fn();
const updatePortalIntegration = vi.fn();
const testPortalConnection = vi.fn();

vi.mock('@/lib/adminApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/adminApi')>('@/lib/adminApi');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      me: (...args: unknown[]) => me(...args),
      getPortalIntegration: (...args: unknown[]) => getPortalIntegration(...args),
      updatePortalIntegration: (...args: unknown[]) => updatePortalIntegration(...args),
      testPortalConnection: (...args: unknown[]) => testPortalConnection(...args),
    },
  };
});

const baseDto = {
  enabled: false,
  base_url: 'https://portal.mns.af',
  api_prefix: '/api/voice-ai/v1',
  client: 'ifilm',
  request_source: 'ifilm',
  connect_timeout_seconds: 3,
  read_timeout_seconds: 5,
  entitlement_ttl_seconds: 900,
  token_configured: true,
  updated_at: '2026-08-19T12:00:00Z',
  last_test_at: null,
  last_test_ok: null,
  config_source: 'db',
};

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LangProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </LangProvider>
    </QueryClientProvider>
  );
}

describe('PortalSettingsPage', () => {
  beforeEach(() => {
    tokenStore.setAdmin('test-token');
    me.mockReset();
    getPortalIntegration.mockReset();
    updatePortalIntegration.mockReset();
    testPortalConnection.mockReset();
  });

  it('denies access without settings permission', async () => {
    me.mockResolvedValue({
      id: 2,
      username: 'catalog',
      email: 'c@test',
      full_name: 'C',
      is_active: true,
      permissions: ['movies.read'],
    });
    wrap(<PortalSettingsPage />);
    expect(
      await screen.findByText(/do not have permission to manage Portal integration settings/i)
    ).toBeInTheDocument();
  });

  it('renders portal settings and shows token as Configured only', async () => {
    me.mockResolvedValue({
      id: 1,
      username: 'admin',
      email: 'a@test',
      full_name: 'Admin',
      is_active: true,
      permissions: ['settings'],
    });
    getPortalIntegration.mockResolvedValue({ ...baseDto });

    wrap(<PortalSettingsPage />);
    expect(await screen.findByTestId('portal-settings-page')).toBeInTheDocument();
    expect(screen.getByTestId('portal-token-status')).toHaveTextContent('Configured');
    expect(screen.queryByDisplayValue(/real-token|Bearer/i)).not.toBeInTheDocument();
    const bodyText = document.body.textContent || '';
    expect(bodyText).not.toMatch(/stored-test-token|Bearer\s+\S+/i);
  });

  it('preserves token when save payload omits blank token', async () => {
    me.mockResolvedValue({
      id: 1,
      username: 'admin',
      permissions: ['settings'],
      is_active: true,
    });
    getPortalIntegration.mockResolvedValue({ ...baseDto });
    updatePortalIntegration.mockResolvedValue({ ...baseDto, client: 'ifilm-updated' });

    wrap(<PortalSettingsPage />);
    await screen.findByTestId('portal-settings-page');
    fireEvent.change(screen.getByLabelText(/Client ID/i), { target: { value: 'ifilm-updated' } });
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }));

    await waitFor(() => expect(updatePortalIntegration).toHaveBeenCalled());
    const payload = updatePortalIntegration.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.token).toBeUndefined();
    expect(payload.client).toBe('ifilm-updated');
  });

  it('replace token flow sends token on save', async () => {
    me.mockResolvedValue({
      id: 1,
      username: 'admin',
      permissions: ['settings'],
      is_active: true,
    });
    getPortalIntegration.mockResolvedValue({ ...baseDto, token_configured: false });
    updatePortalIntegration.mockResolvedValue({ ...baseDto, token_configured: true });

    wrap(<PortalSettingsPage />);
    await screen.findByTestId('portal-settings-page');
    fireEvent.click(screen.getByRole('button', { name: /Replace Token/i }));
    fireEvent.change(screen.getByTestId('portal-token-input'), {
      target: { value: 'new-test-token-not-real' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }));

    await waitFor(() => expect(updatePortalIntegration).toHaveBeenCalled());
    expect(updatePortalIntegration.mock.calls[0][0]).toMatchObject({
      token: 'new-test-token-not-real',
    });
    expect(await screen.findByText(/Portal settings saved/i)).toBeInTheDocument();
  });

  it('runs test connection', async () => {
    me.mockResolvedValue({
      id: 1,
      username: 'admin',
      permissions: ['settings'],
      is_active: true,
    });
    getPortalIntegration.mockResolvedValue({ ...baseDto });
    testPortalConnection.mockResolvedValue({
      ok: true,
      portal_reachable: true,
      credential_accepted: true,
      http_status: 200,
      message: 'Portal reachable and credentials accepted.',
    });

    wrap(<PortalSettingsPage />);
    await screen.findByTestId('portal-settings-page');
    fireEvent.click(screen.getByRole('button', { name: /Test Connection/i }));
    await waitFor(() => expect(testPortalConnection).toHaveBeenCalled());
    expect(await screen.findByText(/credentials accepted/i)).toBeInTheDocument();
  });

  it('blocks save when enabling without token', async () => {
    me.mockResolvedValue({
      id: 1,
      username: 'admin',
      permissions: ['settings'],
      is_active: true,
    });
    getPortalIntegration.mockResolvedValue({ ...baseDto, token_configured: false, enabled: false });

    wrap(<PortalSettingsPage />);
    await screen.findByTestId('portal-settings-page');
    fireEvent.click(screen.getByTestId('portal-enabled-switch'));
    expect(await screen.findByText(/Token required/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save Changes/i })).toBeDisabled();
  });
});
