/** Admin CDN + storage API client (CDN-P1). Secret-free DTOs only. */
import { ADMIN_UNAUTHORIZED_EVENT, createHttp, tokenStore } from '@/lib/api';

function clearAdminAndNotify() {
  tokenStore.clearAdmin();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(ADMIN_UNAUTHORIZED_EVENT));
  }
}

const http = createHttp(() => tokenStore.getAdmin(), { onUnauthorized: clearAdminAndNotify });

const BASE = '/admin/cdn-management';

export type StorageProvider = 'cloudflare_r2' | 's3_compatible';

export type StorageSettingsDto = {
  enabled: boolean;
  provider: StorageProvider;
  endpoint_url: string;
  account_id?: string | null;
  bucket: string;
  region: string;
  object_key_prefix: string;
  credentials_configured: boolean;
  updated_at?: string | null;
  last_test_at?: string | null;
  last_test_ok?: boolean | null;
  last_test_reachable?: boolean | null;
  last_test_bucket_accessible?: boolean | null;
  last_test_message?: string | null;
};

export type StorageSettingsPayload = {
  enabled: boolean;
  provider: StorageProvider;
  endpoint_url: string;
  account_id?: string;
  bucket: string;
  region: string;
  object_key_prefix: string;
  access_key_id?: string;
  secret_access_key?: string;
  remove_credentials?: boolean;
};

export type StorageTestDto = {
  ok: boolean;
  reachable: boolean;
  bucket_accessible: boolean;
  endpoint_host?: string | null;
  message: string;
  tested_at: string;
  settings: StorageSettingsDto;
};

export type NodeRole = 'main' | 'cache';
export type NodeState = 'online' | 'offline' | 'draining' | 'provisioning' | 'failed' | 'disabled';

export type CDNNodeDto = {
  id: string;
  name: string;
  role: NodeRole;
  role_label: string;
  host: string;
  ssh_port: number;
  ssh_username: string;
  credential_type: string;
  credential_configured: boolean;
  managed_key_configured: boolean;
  managed_key_fingerprint?: string | null;
  ssh_host_key_fingerprint?: string | null;
  observed_host_key_fingerprint?: string | null;
  heartbeat_token_configured: boolean;
  branch?: string | null;
  location?: string | null;
  notes?: string | null;
  enabled: boolean;
  draining: boolean;
  is_default: boolean;
  priority: number;
  serve_base_url?: string | null;
  cache_limit_bytes?: number | null;
  storage_limit_bytes?: number | null;
  high_watermark_pct: number;
  low_watermark_pct: number;
  disk_total_bytes?: number | null;
  disk_used_bytes?: number | null;
  disk_free_bytes?: number | null;
  cache_used_bytes?: number | null;
  cache_utilization_pct?: number | null;
  cached_objects: number;
  cached_titles: number;
  cache_hits: number;
  cache_misses: number;
  hit_rate?: number | null;
  bandwidth_bytes: number;
  rtt_ms?: number | null;
  software_version?: string | null;
  os_release?: string | null;
  health_status: string;
  state: NodeState;
  online: boolean;
  heartbeat_age_seconds?: number | null;
  provision_status: string;
  provisioned_at?: string | null;
  last_error?: string | null;
  last_error_at?: string | null;
  last_ssh_test_at?: string | null;
  last_ssh_test_ok?: boolean | null;
  last_heartbeat_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type CDNNodePayload = {
  name: string;
  role: NodeRole;
  host: string;
  ssh_port: number;
  ssh_username: string;
  credential_type?: 'password' | 'private_key';
  credential?: string;
  remove_credential?: boolean;
  branch?: string;
  location?: string;
  notes?: string;
  enabled?: boolean;
  is_default?: boolean;
  priority?: number;
  serve_base_url?: string;
  cache_limit_bytes?: number | null;
  high_watermark_pct?: number;
  low_watermark_pct?: number;
};

export type CDNNodeCreatedDto = { node: CDNNodeDto; heartbeat_token: string | null };

export type SSHTestDto = {
  ok: boolean;
  code: string;
  detail: string;
  host_key_fingerprint?: string;
  host_key_pinned?: boolean;
  os_release?: string;
  debian13?: boolean;
  privileged?: boolean;
  disk_total_bytes?: number;
  disk_free_bytes?: number;
  rtt_ms?: number;
  node?: CDNNodeDto;
};

export type ProvisionRunDto = {
  id: string;
  node_id: string;
  action: string;
  status: string;
  step?: string | null;
  attempt: number;
  error_code?: string | null;
  resume_from_step?: string | null;
  log: string;
  claimed_by?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
};

export type CDNRouteDto = {
  id: string;
  cidr: string;
  prefix_length: number;
  node_id: string;
  node_name?: string | null;
  node_role?: string | null;
  priority: number;
  enabled: boolean;
  notes?: string | null;
};

export type CDNRoutePayload = { cidr: string; node_id: string; priority: number; enabled: boolean; notes?: string | null };

export type RouteChainEntry = {
  stage: string;
  node_id: string | null;
  node_name: string;
  role: string;
  role_label: string;
  branch?: string | null;
  matched_cidr?: string | null;
  rule_priority?: number | null;
  node_priority?: number | null;
  eligible: boolean;
  reason: string;
  state: string;
  serve_base_url?: string | null;
};

export type RouteLookupDto = {
  client_ip: string;
  matched_cidr: string | null;
  selected: CDNNodeDto | null;
  selected_stage: string;
  reason: string;
  chain: RouteChainEntry[];
  edge_routing_enabled: boolean;
  central_fallback: boolean;
};

export type CDNFlagsDto = {
  enable_cdn_node_api: boolean;
  enable_cdn_provisioning: boolean;
  enable_cdn_edge_routing: boolean;
  edge_routing_phase: string;
  customer_playback_route: string;
  heartbeat_stale_seconds: number;
  integration_secrets_configured: boolean;
  edge_grant_public_key_configured: boolean;
  legacy_cdn_sync_enabled: boolean;
};

export type CDNOverviewDto = {
  generated_at: string;
  flags: CDNFlagsDto;
  totals: {
    nodes: number;
    online: number;
    offline: number;
    draining: number;
    provisioning: number;
    failed: number;
    disabled: number;
    main_nodes: number;
    cache_nodes: number;
    routes: number;
    routes_enabled: number;
  };
  main_cdn: { default_node: CDNNodeDto | null; status: string; secondary_online: number };
  storage: {
    disk_total_bytes: number;
    disk_used_bytes: number;
    disk_free_bytes: number;
    cache_limit_bytes: number;
    cache_used_bytes: number;
  };
  cache: { hits: number; misses: number; hit_rate: number | null; bandwidth_bytes: number };
  network?: NetworkSettingsDto;
  recent_provisioning_failures: (ProvisionRunDto & { node_name: string })[];
  central_fallback: string;
};

export type NetworkSettingsDto = {
  management_cidrs: string[];
  serve_cidrs: string[];
  source: 'db' | 'env' | 'unset';
  management_configured: boolean;
  management_allow_any: boolean;
  serve_allow_any: boolean;
  media_port_open: boolean;
  provisioning_ready: boolean;
  updated_at?: string | null;
};

export type NetworkSettingsPayload = { management_cidrs: string[]; serve_cidrs: string[]; confirm_allow_any?: boolean };

export type NodeAction =
  | 'provision'
  | 'reprovision'
  | 'upgrade'
  | 'drain'
  | 'undrain'
  | 'disable'
  | 'enable'
  | 'clear-cache';

export const cdnApi = {
  async getStorage(): Promise<StorageSettingsDto> {
    return (await http.get<StorageSettingsDto>(`${BASE}/r2`)).data;
  },
  async updateStorage(payload: StorageSettingsPayload): Promise<StorageSettingsDto> {
    return (await http.put<StorageSettingsDto>(`${BASE}/r2`, payload)).data;
  },
  async testStorage(): Promise<StorageTestDto> {
    return (await http.post<StorageTestDto>(`${BASE}/r2/test`)).data;
  },
  async getNetwork(): Promise<NetworkSettingsDto> {
    return (await http.get<NetworkSettingsDto>(`${BASE}/network`)).data;
  },
  async updateNetwork(payload: NetworkSettingsPayload): Promise<NetworkSettingsDto> {
    return (await http.put<NetworkSettingsDto>(`${BASE}/network`, payload)).data;
  },
  async flags(): Promise<CDNFlagsDto> {
    return (await http.get<CDNFlagsDto>(`${BASE}/status`)).data;
  },
  async overview(): Promise<CDNOverviewDto> {
    return (await http.get<CDNOverviewDto>(`${BASE}/overview`)).data;
  },
  async listNodes(): Promise<CDNNodeDto[]> {
    return (await http.get<CDNNodeDto[]>(`${BASE}/nodes`)).data;
  },
  async getNode(id: string): Promise<CDNNodeDto> {
    return (await http.get<CDNNodeDto>(`${BASE}/nodes/${id}`)).data;
  },
  async createNode(payload: CDNNodePayload): Promise<CDNNodeCreatedDto> {
    return (await http.post<CDNNodeCreatedDto>(`${BASE}/nodes`, payload)).data;
  },
  async updateNode(id: string, payload: Partial<CDNNodePayload>): Promise<CDNNodeDto> {
    return (await http.patch<CDNNodeDto>(`${BASE}/nodes/${id}`, payload)).data;
  },
  async deleteNode(id: string): Promise<void> {
    await http.delete(`${BASE}/nodes/${id}`, { params: { confirm: true } });
  },
  async testSsh(id: string): Promise<SSHTestDto> {
    return (await http.post<SSHTestDto>(`${BASE}/nodes/${id}/test-ssh`)).data;
  },
  async pinHostKey(id: string, fingerprint: string): Promise<CDNNodeDto> {
    return (await http.post<CDNNodeDto>(`${BASE}/nodes/${id}/pin-host-key`, { fingerprint, confirm: true })).data;
  },
  async nodeAction(id: string, action: NodeAction): Promise<ProvisionRunDto | { node: CDNNodeDto }> {
    return (await http.post(`${BASE}/nodes/${id}/actions/${action}`, { confirm: true })).data;
  },
  async rotateNodeToken(id: string): Promise<{ heartbeat_token: string }> {
    return (await http.post<{ heartbeat_token: string }>(`${BASE}/nodes/${id}/heartbeat-token`, { confirm: true })).data;
  },
  async provisionRuns(id: string): Promise<ProvisionRunDto[]> {
    return (await http.get<ProvisionRunDto[]>(`${BASE}/nodes/${id}/provision-runs`)).data;
  },
  async listRoutes(): Promise<CDNRouteDto[]> {
    return (await http.get<CDNRouteDto[]>(`${BASE}/routes`)).data;
  },
  async createRoute(payload: CDNRoutePayload): Promise<CDNRouteDto> {
    return (await http.post<CDNRouteDto>(`${BASE}/routes`, payload)).data;
  },
  async updateRoute(id: string, payload: Partial<CDNRoutePayload>): Promise<CDNRouteDto> {
    return (await http.patch<CDNRouteDto>(`${BASE}/routes/${id}`, payload)).data;
  },
  async deleteRoute(id: string): Promise<void> {
    await http.delete(`${BASE}/routes/${id}`, { params: { confirm: true } });
  },
  async lookupRoute(clientIp: string): Promise<RouteLookupDto> {
    return (await http.post<RouteLookupDto>(`${BASE}/routes/lookup`, { client_ip: clientIp })).data;
  },
};
