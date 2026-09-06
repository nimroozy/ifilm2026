import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import CDNOverviewPage from '../cdn/CDNOverviewPage';
import CDNServersPage from '../cdn/CDNServersPage';
import CDNRoutingPage from '../cdn/CDNRoutingPage';
import CDNHealthPage from '../cdn/CDNHealthPage';
import type { CDNNodeDto } from '@/lib/cdnApi';

const api = vi.hoisted(() => ({
  overview: vi.fn(),
  listNodes: vi.fn(),
  createNode: vi.fn(),
  updateNode: vi.fn(),
  deleteNode: vi.fn(),
  testSsh: vi.fn(),
  pinHostKey: vi.fn(),
  nodeAction: vi.fn(),
  provisionRuns: vi.fn(),
  listRoutes: vi.fn(),
  createRoute: vi.fn(),
  updateRoute: vi.fn(),
  deleteRoute: vi.fn(),
  lookupRoute: vi.fn(),
  getNetwork: vi.fn(),
  updateNetwork: vi.fn(),
}));

vi.mock('@/lib/cdnApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/cdnApi')>('@/lib/cdnApi');
  return { ...actual, cdnApi: { ...actual.cdnApi, ...api } };
});

const node: CDNNodeDto = {
  id: 'n1',
  name: 'Nimruz Cache',
  role: 'cache',
  role_label: 'CACHE',
  host: '203.0.113.31',
  ssh_port: 22,
  ssh_username: 'root',
  credential_type: 'password',
  credential_configured: true,
  managed_key_configured: false,
  heartbeat_token_configured: true,
  branch: 'nimruz',
  enabled: true,
  draining: false,
  is_default: false,
  priority: 100,
  serve_base_url: 'https://203.0.113.31:8443',
  cache_limit_bytes: 500 * 1024 ** 3,
  high_watermark_pct: 90,
  low_watermark_pct: 80,
  disk_total_bytes: 1000 * 1024 ** 3,
  disk_used_bytes: 300 * 1024 ** 3,
  disk_free_bytes: 700 * 1024 ** 3,
  cache_used_bytes: 250 * 1024 ** 3,
  cache_utilization_pct: 50,
  cached_objects: 1200,
  cached_titles: 40,
  cache_hits: 900,
  cache_misses: 100,
  hit_rate: 90,
  bandwidth_bytes: 42 * 1024 ** 3,
  software_version: '1.0.0+abc',
  health_status: 'online',
  state: 'online',
  online: true,
  heartbeat_age_seconds: 12,
  provision_status: 'ready',
  ssh_host_key_fingerprint: 'SHA256:pinnedpinnedpinnedpinnedpinnedpinnedpinnedA',
};

const mainNode: CDNNodeDto = { ...node, id: 'm1', name: 'Kabul Main', role: 'main', role_label: 'MAIN_CDN', host: '203.0.113.10', is_default: true, state: 'offline', online: false, heartbeat_age_seconds: 4000, provision_status: 'not_started', ssh_host_key_fingerprint: null };

const closedNetwork = {
  management_cidrs: [] as string[],
  serve_cidrs: [] as string[],
  source: 'unset' as const,
  management_configured: false,
  management_allow_any: false,
  serve_allow_any: false,
  media_port_open: false,
  provisioning_ready: false,
  updated_at: null,
};

function wrap(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe('CDN admin pages', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.listNodes.mockResolvedValue([mainNode, node]);
    api.getNetwork.mockResolvedValue(closedNetwork);
    api.listRoutes.mockResolvedValue([{ id: 'r1', cidr: '103.126.4.0/24', prefix_length: 24, node_id: 'n1', node_name: 'Nimruz Cache', node_role: 'cache', priority: 100, enabled: true, notes: 'Nimruz branch' }]);
    api.provisionRuns.mockResolvedValue([{ id: 'run1', node_id: 'n1', action: 'provision', status: 'failed', step: 'packages', attempt: 1, error_code: 'apt_install_failed', log: '[10:00:00] == packages\n[10:00:01] FAILED', created_at: '2026-09-06T10:00:00Z' }]);
  });

  it('overview shows totals, main status and the edge-routing notice', async () => {
    api.overview.mockResolvedValue({
      generated_at: '2026-09-06T12:00:00Z',
      flags: { enable_cdn_node_api: true, enable_cdn_provisioning: true, enable_cdn_edge_routing: false, edge_routing_phase: 'CDN-P2 (not enabled)', customer_playback_route: '/api/stream/{token}/... (central)', heartbeat_stale_seconds: 90, integration_secrets_configured: true, edge_grant_public_key_configured: false, legacy_cdn_sync_enabled: false },
      totals: { nodes: 2, online: 1, offline: 1, draining: 0, provisioning: 0, failed: 0, disabled: 0, main_nodes: 1, cache_nodes: 1, routes: 3, routes_enabled: 2 },
      main_cdn: { default_node: mainNode, status: 'offline', secondary_online: 0 },
      storage: { disk_total_bytes: 2000 * 1024 ** 3, disk_used_bytes: 600 * 1024 ** 3, disk_free_bytes: 1400 * 1024 ** 3, cache_limit_bytes: 500 * 1024 ** 3, cache_used_bytes: 250 * 1024 ** 3 },
      cache: { hits: 900, misses: 100, hit_rate: 90, bandwidth_bytes: 1024 ** 3 },
      recent_provisioning_failures: [{ id: 'run1', node_id: 'n1', node_name: 'Nimruz Cache', action: 'provision', status: 'failed', step: 'packages', attempt: 1, error_code: 'apt_install_failed', log: '', created_at: '2026-09-06T10:00:00Z' }],
      central_fallback: 'always',
    });
    wrap(<CDNOverviewPage />);
    await waitFor(() => expect(screen.getByTestId('cdn-overview-page')).toBeInTheDocument());
    expect(screen.getByTestId('cdn-stat-nodes').textContent).toContain('2');
    expect(screen.getByTestId('cdn-stat-online').textContent).toContain('1');
    expect(screen.getByTestId('cdn-stat-hit-ratio').textContent).toContain('90.0%');
    expect(screen.getByTestId('cdn-stat-routes').textContent).toContain('3');
    expect(screen.getByTestId('cdn-edge-routing-notice').textContent).toContain('/api/stream/');
    expect(screen.getByTestId('cdn-recent-failures').textContent).toContain('apt_install_failed');
    expect(screen.getByTestId('cdn-state-offline')).toBeInTheDocument();
  });

  it('servers page lists badges, adds a server, tests SSH, pins host key and confirms actions', async () => {
    api.createNode.mockResolvedValue({ node: { ...node, id: 'n2', name: 'Herat Cache', state: 'offline', provision_status: 'not_started', ssh_host_key_fingerprint: null }, heartbeat_token: 'one-time-token' });
    api.testSsh.mockResolvedValue({ ok: true, code: 'ok', detail: 'SSH authentication succeeded', host_key_fingerprint: 'SHA256:observedobservedobservedobservedobservedAAA', host_key_pinned: false, os_release: 'debian 13', debian13: true, privileged: true, disk_free_bytes: 70 * 1024 ** 3 });
    api.pinHostKey.mockResolvedValue(mainNode);
    api.nodeAction.mockResolvedValue({ node });
    wrap(<CDNServersPage />);
    await waitFor(() => expect(screen.getByTestId('cdn-servers-page')).toBeInTheDocument());
    expect(screen.getAllByText('MAIN CDN').length).toBeGreaterThan(0);
    expect(screen.getAllByText('CACHE').length).toBeGreaterThan(0);
    expect(screen.getByTestId('cdn-state-online')).toBeInTheDocument();
    expect(screen.getByTestId('cdn-state-offline')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('cdn-add-server'));
    fireEvent.change(screen.getByTestId('node-name'), { target: { value: 'Herat Cache' } });
    fireEvent.change(screen.getByTestId('node-host'), { target: { value: '203.0.113.40' } });
    fireEvent.change(screen.getByTestId('node-credential'), { target: { value: 'bootstrap-secret' } });
    fireEvent.click(screen.getByTestId('node-save'));
    await waitFor(() => expect(api.createNode).toHaveBeenCalledTimes(1));
    const payload = api.createNode.mock.calls[0][0];
    expect(payload).toMatchObject({ name: 'Herat Cache', host: '203.0.113.40', credential: 'bootstrap-secret', role: 'cache', cache_limit_bytes: 500 * 1024 ** 3 });
    await waitFor(() => expect(screen.getByTestId('cdn-token-reveal')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('cdn-node-select-m1'));
    await waitFor(() => expect(screen.getByTestId('cdn-node-detail')).toBeInTheDocument());
    expect((screen.getByTestId('cdn-action-provision') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId('cdn-action-test-ssh'));
    await waitFor(() => expect(screen.getByTestId('cdn-ssh-result')).toBeInTheDocument());
    expect(screen.getByTestId('cdn-ssh-fingerprint').textContent).toContain('SHA256:observed');
    fireEvent.click(screen.getByTestId('cdn-pin-host-key'));
    await waitFor(() => expect(api.pinHostKey).toHaveBeenCalledWith('m1', 'SHA256:observedobservedobservedobservedobservedAAA'));

    fireEvent.click(screen.getByTestId('cdn-node-select-n1'));
    await waitFor(() => expect(screen.getByTestId('cdn-provision-runs').textContent).toContain('apt_install_failed'));
    fireEvent.click(screen.getByTestId('cdn-action-disable'));
    await waitFor(() => expect(screen.getByTestId('cdn-confirm-dialog')).toBeInTheDocument());
    expect(api.nodeAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('cdn-confirm-action'));
    await waitFor(() => expect(api.nodeAction).toHaveBeenCalledWith('n1', 'disable'));
    expect(document.body.textContent).not.toContain('bootstrap-secret');
  });

  it('routing page adds rules, requires confirmation to delete, and shows the fallback chain', async () => {
    api.createRoute.mockResolvedValue({});
    api.deleteRoute.mockResolvedValue(undefined);
    api.lookupRoute.mockResolvedValue({
      client_ip: '103.126.4.55',
      matched_cidr: '103.126.4.0/24',
      selected: null,
      selected_stage: 'central',
      reason: 'central_fallback',
      edge_routing_enabled: false,
      central_fallback: true,
      chain: [
        { stage: 'preferred_rule', node_id: 'n1', node_name: 'Nimruz Cache', role: 'cache', role_label: 'CACHE', matched_cidr: '103.126.4.0/24', eligible: false, reason: 'stale_heartbeat', state: 'offline' },
        { stage: 'default_main', node_id: 'm1', node_name: 'Kabul Main', role: 'main', role_label: 'MAIN_CDN', eligible: false, reason: 'not_provisioned', state: 'offline' },
        { stage: 'central', node_id: null, node_name: 'iFilm central', role: 'central', role_label: 'CENTRAL', eligible: true, reason: 'always_available', state: 'central' },
      ],
    });
    wrap(<CDNRoutingPage />);
    await waitFor(() => expect(screen.getByTestId('cdn-routing-page')).toBeInTheDocument());
    expect(screen.getByTestId('route-row-r1').textContent).toContain('103.126.4.0/24');
    expect(screen.getByTestId('route-row-r1').textContent).toContain('Nimruz branch');

    fireEvent.click(screen.getByLabelText('Delete 103.126.4.0/24'));
    expect(api.deleteRoute).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId('route-delete-confirm'));
    await waitFor(() => expect(api.deleteRoute).toHaveBeenCalledWith('r1'));

    fireEvent.change(screen.getByTestId('route-test-ip'), { target: { value: '103.126.4.55' } });
    fireEvent.click(screen.getByTestId('route-test-run'));
    await waitFor(() => expect(screen.getByTestId('route-test-result')).toBeInTheDocument());
    const result = within(screen.getByTestId('route-test-result'));
    expect(result.getByText('Central iFilm playback')).toBeInTheDocument();
    expect(result.getByText('stale_heartbeat')).toBeInTheDocument();
    expect(result.getByText('not_provisioned')).toBeInTheDocument();
    expect(result.getAllByText('Central iFilm').length).toBeGreaterThan(0);
  });

  it('health page renders metrics per node', async () => {
    wrap(<CDNHealthPage />);
    await waitFor(() => expect(screen.getByTestId('cdn-health-page')).toBeInTheDocument());
    const row = screen.getByTestId('cdn-health-row-n1');
    expect(row.textContent).toContain('1.0.0+abc');
    expect(row.textContent).toContain('90.0%');
    expect(row.textContent).toContain('1200');
    expect(row.textContent).toContain('250.0 GB');
  });

  it('network card fails closed, requires management CIDRs, and confirms allow-any', async () => {
    api.updateNetwork.mockImplementation(async (payload: { management_cidrs: string[]; serve_cidrs: string[]; confirm_allow_any?: boolean }) => ({
      ...closedNetwork,
      management_cidrs: payload.management_cidrs,
      serve_cidrs: payload.serve_cidrs,
      source: 'db' as const,
      management_configured: true,
      provisioning_ready: true,
      media_port_open: payload.serve_cidrs.length > 0,
      serve_allow_any: payload.serve_cidrs.includes('0.0.0.0/0'),
      management_allow_any: false,
    }));
    wrap(<CDNServersPage />);
    await waitFor(() => expect(screen.getByTestId('cdn-network-card')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('cdn-network-missing')).toBeInTheDocument());
    expect(screen.getByTestId('cdn-media-port-badge').textContent).toContain('media port closed');
    expect((screen.getByTestId('cdn-management-cidrs') as HTMLTextAreaElement).value).toBe('');
    expect((screen.getByTestId('cdn-serve-cidrs') as HTMLTextAreaElement).value).toBe('');
    expect((screen.getByTestId('cdn-network-save') as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByTestId('cdn-management-cidrs'), { target: { value: '203.0.113.10/32\n2001:db8::/32' } });
    fireEvent.click(screen.getByTestId('cdn-network-save'));
    await waitFor(() => expect(api.updateNetwork).toHaveBeenCalledTimes(1));
    expect(api.updateNetwork.mock.calls[0][0]).toEqual({ management_cidrs: ['203.0.113.10/32', '2001:db8::/32'], serve_cidrs: [], confirm_allow_any: false });
    await waitFor(() => expect(screen.getByTestId('cdn-media-port-badge').textContent).toContain('media port closed'));

    fireEvent.change(screen.getByTestId('cdn-serve-cidrs'), { target: { value: '0.0.0.0/0' } });
    expect(screen.getByTestId('cdn-network-allow-any-warning')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('cdn-network-save'));
    await waitFor(() => expect(screen.getByTestId('cdn-network-confirm')).toBeInTheDocument());
    expect(api.updateNetwork).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('cdn-network-confirm-action'));
    await waitFor(() => expect(api.updateNetwork).toHaveBeenCalledTimes(2));
    expect(api.updateNetwork.mock.calls[1][0]).toMatchObject({ serve_cidrs: ['0.0.0.0/0'], confirm_allow_any: true });
  });
});
