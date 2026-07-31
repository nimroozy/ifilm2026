import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, LangProvider } from '@/components/CustomerLayout';
import { LoginPage, ProfilePage, DevicesPage } from '@/pages/Account';
import { ApiError, clearSensitiveAuthState, tokenStore } from '@/lib/api';

const apiMocks = vi.hoisted(() => ({
  login: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
  entitlement: vi.fn(),
  listDevices: vi.fn(),
  revokeDevice: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock('@/lib/dataMode', () => ({
  isMockMode: () => false,
}));

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    api: {
      ...actual.api,
      login: (...args: unknown[]) => apiMocks.login(...args),
      logout: (...args: unknown[]) => apiMocks.logout(...args),
      me: (...args: unknown[]) => apiMocks.me(...args),
      entitlement: (...args: unknown[]) => apiMocks.entitlement(...args),
      listDevices: (...args: unknown[]) => apiMocks.listDevices(...args),
      revokeDevice: (...args: unknown[]) => apiMocks.revokeDevice(...args),
      refresh: (...args: unknown[]) => apiMocks.refresh(...args),
    },
  };
});

function wrap(ui: ReactNode) {
  return (
    <MemoryRouter>
      <LangProvider>
        <AuthProvider>{ui}</AuthProvider>
      </LangProvider>
    </MemoryRouter>
  );
}

describe('subscriber auth UI', () => {
  beforeEach(() => {
    tokenStore.clear();
    Object.values(apiMocks).forEach((fn) => fn.mockReset());
    apiMocks.me.mockResolvedValue({
      id: 1,
      username: 'mobin_user_001',
      name: 'Ahmad Karimi',
      branch: 'Kabul',
      package: 'Premium 50Mbps',
      expiration: '2026-12-31',
      status: 'active',
      service_status: 'active',
      max_devices: 3,
    });
    apiMocks.entitlement.mockResolvedValue({
      allowed: true,
      account_status: 'active',
      service_status: 'active',
      package_name: 'Premium 50Mbps',
      branch_code: 'Kabul',
      max_devices: 3,
      source: 'fixture',
    });
    apiMocks.listDevices.mockResolvedValue([
      {
        id: 11,
        client_device_id: 'abc',
        name: 'Browser',
        device_type: 'desktop',
        browser: 'Test',
        ip: '127.0.0.1',
        current: true,
      },
    ]);
  });

  it('logs in against real APIs and stores tokens', async () => {
    apiMocks.login.mockImplementation(async () => {
      tokenStore.set('access');
      tokenStore.setRefresh('refresh');
      return {
        access_token: 'access',
        refresh_token: 'refresh',
        token_type: 'bearer',
      };
    });
    render(wrap(<LoginPage />));
    fireEvent.change(screen.getByLabelText(/نام کاربری|username/i), {
      target: { value: 'mobin_user_001' },
    });
    fireEvent.change(screen.getByLabelText(/رمز|password/i), {
      target: { value: 'fixture-pass-ok' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ورود|sign in/i }));
    await waitFor(() => expect(apiMocks.login).toHaveBeenCalled());
    await waitFor(() => expect(tokenStore.get()).toBe('access'));
    expect(tokenStore.getRefresh()).toBe('refresh');
    expect(apiMocks.me).toHaveBeenCalled();
  });

  it('shows safe suspended login error', async () => {
    apiMocks.login.mockRejectedValue(
      new ApiError('denied', 403, { code: 'account_suspended', message: 'suspended' }),
    );
    render(wrap(<LoginPage />));
    fireEvent.change(screen.getByLabelText(/نام کاربری|username/i), { target: { value: 'sus' } });
    fireEvent.change(screen.getByLabelText(/رمز|password/i), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: /ورود|sign in/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/suspended/i);
    expect(tokenStore.get()).toBeNull();
  });

  it('loads profile from API without mock fallback', async () => {
    tokenStore.set('tok');
    tokenStore.setRefresh('ref');
    render(wrap(<ProfilePage />));
    expect(await screen.findByText('@mobin_user_001')).toBeInTheDocument();
    expect(screen.getByText('Premium 50Mbps')).toBeInTheDocument();
  });

  it('lists and revokes devices via API', async () => {
    tokenStore.set('tok');
    apiMocks.listDevices.mockResolvedValue([
      {
        id: 22,
        client_device_id: 'other',
        name: 'Old Phone',
        device_type: 'mobile',
        browser: 'Mobile',
        ip: '10.0.0.2',
        current: false,
      },
    ]);
    apiMocks.revokeDevice.mockResolvedValue({ detail: 'Device revoked' });
    render(wrap(<DevicesPage />));
    expect(await screen.findByText('Old Phone')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Remove Old Phone/i));
    fireEvent.click(screen.getByRole('button', { name: /حذف|remove/i }));
    await waitFor(() => expect(apiMocks.revokeDevice).toHaveBeenCalledWith(22));
  });

  it('clears sensitive tokens on logout helper', () => {
    tokenStore.set('tok');
    tokenStore.setRefresh('ref');
    clearSensitiveAuthState();
    expect(tokenStore.get()).toBeNull();
    expect(tokenStore.getRefresh()).toBeNull();
  });
});
