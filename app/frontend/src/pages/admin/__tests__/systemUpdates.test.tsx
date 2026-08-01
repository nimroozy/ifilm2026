import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SystemUpdatesPage from '../SystemUpdatesPage';
import { tokenStore } from '@/lib/api';
import { LangProvider } from '@/components/CustomerLayout';

const me = vi.fn();
const getSystemVersion = vi.fn();
const checkSystemUpdates = vi.fn();
const runSystemUpdatePreflight = vi.fn();
const installSystemUpdate = vi.fn();
const listSystemUpdateHistory = vi.fn();
const getSystemUpdateJob = vi.fn();
const rollbackSystemUpdate = vi.fn();
const createSystemUpdateBackup = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      me: (...args: unknown[]) => me(...args),
      getSystemVersion: (...args: unknown[]) => getSystemVersion(...args),
      checkSystemUpdates: (...args: unknown[]) => checkSystemUpdates(...args),
      runSystemUpdatePreflight: (...args: unknown[]) => runSystemUpdatePreflight(...args),
      installSystemUpdate: (...args: unknown[]) => installSystemUpdate(...args),
      listSystemUpdateHistory: (...args: unknown[]) => listSystemUpdateHistory(...args),
      getSystemUpdateJob: (...args: unknown[]) => getSystemUpdateJob(...args),
      rollbackSystemUpdate: (...args: unknown[]) => rollbackSystemUpdate(...args),
      createSystemUpdateBackup: (...args: unknown[]) => createSystemUpdateBackup(...args),
    },
  };
});

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

describe('SystemUpdatesPage', () => {
  beforeEach(() => {
    tokenStore.setAdmin('test-token');
    me.mockReset();
    getSystemVersion.mockReset();
    checkSystemUpdates.mockReset();
    runSystemUpdatePreflight.mockReset();
    installSystemUpdate.mockReset();
    listSystemUpdateHistory.mockReset();
    getSystemUpdateJob.mockReset();
    rollbackSystemUpdate.mockReset();
    createSystemUpdateBackup.mockReset();
    window.confirm = vi.fn(() => true);
  });

  it('denies access without permission', async () => {
    me.mockResolvedValue({
      id: 2,
      username: 'catalog',
      email: 'c@test',
      full_name: 'C',
      is_active: true,
      permissions: ['movies.read'],
    });
    wrap(<SystemUpdatesPage />);
    expect(await screen.findByText(/Permission denied/i)).toBeInTheDocument();
  });

  it('checks updates and shows release notes', async () => {
    me.mockResolvedValue({
      id: 1,
      username: 'admin',
      email: 'a@test',
      full_name: 'Admin',
      is_active: true,
      permissions: ['system_updates.read', 'system_updates.manage'],
    });
    getSystemVersion.mockResolvedValue({
      version: '0.1.0-test',
      build_commit: 'abc12345',
      deployment_mode: 'staging',
      update_channel: 'stable',
      maintenance_mode: false,
      migration_head: '011_system_updates',
    });
    listSystemUpdateHistory.mockResolvedValue({ items: [], total: 0 });
    checkSystemUpdates.mockResolvedValue({
      update_available: true,
      channel: 'stable',
      current: { version: '0.1.0-test' },
      latest: {
        version: '0.1.1-test',
        published_at: '2026-08-02T00:00:00Z',
        notes: 'Fixes and migrations',
      },
    });

    wrap(<SystemUpdatesPage />);
    expect(await screen.findByText('0.1.0-test')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Check for Updates/i }));
    await waitFor(() => expect(checkSystemUpdates).toHaveBeenCalled());
    expect(await screen.findByText('0.1.1-test')).toBeInTheDocument();
    expect(screen.getByText(/Fixes and migrations/)).toBeInTheDocument();
  });

  it('requires password before install', async () => {
    me.mockResolvedValue({
      id: 1,
      username: 'admin',
      email: 'a@test',
      full_name: 'Admin',
      is_active: true,
      permissions: ['system_updates.read', 'system_updates.manage'],
    });
    getSystemVersion.mockResolvedValue({
      version: '0.1.0-test',
      build_commit: 'abc',
      deployment_mode: 'staging',
      update_channel: 'stable',
      maintenance_mode: false,
    });
    listSystemUpdateHistory.mockResolvedValue({ items: [], total: 0 });
    checkSystemUpdates.mockResolvedValue({
      update_available: true,
      channel: 'stable',
      current: { version: '0.1.0-test' },
      latest: { version: '0.1.1-test', notes: 'n' },
    });

    wrap(<SystemUpdatesPage />);
    await screen.findByText('0.1.0-test');
    fireEvent.click(screen.getByRole('button', { name: /Check for Updates/i }));
    await screen.findByText('0.1.1-test');
    fireEvent.click(screen.getByRole('button', { name: /Install Update/i }));
    expect(await screen.findByText(/Re-enter your admin password/i)).toBeInTheDocument();
    expect(installSystemUpdate).not.toHaveBeenCalled();
  });

  it('shows no update state', async () => {
    me.mockResolvedValue({
      id: 1,
      username: 'admin',
      email: 'a@test',
      full_name: 'Admin',
      is_active: true,
      permissions: ['system_updates.read', 'system_updates.manage'],
    });
    getSystemVersion.mockResolvedValue({
      version: '0.1.1-test',
      build_commit: 'def',
      deployment_mode: 'production',
      update_channel: 'stable',
      maintenance_mode: false,
    });
    listSystemUpdateHistory.mockResolvedValue({ items: [], total: 0 });
    checkSystemUpdates.mockResolvedValue({
      update_available: false,
      channel: 'stable',
      current: { version: '0.1.1-test' },
      latest: null,
    });
    wrap(<SystemUpdatesPage />);
    fireEvent.click(await screen.findByRole('button', { name: /Check for Updates/i }));
    expect(await screen.findByText(/No update available/i)).toBeInTheDocument();
  });
});
