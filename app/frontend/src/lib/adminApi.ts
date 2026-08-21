/** Admin-only API client. Do not import from customer home entry. */
import {
  ADMIN_UNAUTHORIZED_EVENT,
  createHttp,
  tokenStore,
  unwrapList,
  type Envelope,
  type AdminCollectionListParams,
  type AdminUserDto,
  type CatalogEntityType,
  type CollectionCreatePayload,
  type CollectionDto,
  type CollectionItemAddPayload,
  type CollectionItemDto,
  type CollectionPickerParams,
  type CollectionPickerResultDto,
  type CollectionUpdatePayload,
  type DashboardStatsDto,
  type EncodingProfileDto,
  type EpisodeCreatePayload,
  type EpisodeDto,
  type EpisodeUpdatePayload,
  type GenreCreatePayload,
  type GenreDto,
  type GenreUpdatePayload,
  type MediaAssetDto,
  type MediaAssetUsageDto,
  type MediaCategory,
  type MediaPackageDto,
  type MediaStorageHealthDto,
  type MovieCreatePayload,
  type MovieDto,
  type MovieUpdatePayload,
  type PlaybackSessionCreatedDto,
  type PlaybackSessionDto,
  type ProcessingJobDto,
  type PublicationActionDto,
  type PublicationHistoryEventDto,
  type PublicationReadinessDto,
  type RecommendationInspectDto,
  type ContentRequestAdminActionBody,
  type ContentRequestAdminDetailDto,
  type ContentRequestAdminListDto,
  type ContentRequestDto,
  type SeasonCreatePayload,
  type SeasonDto,
  type SeasonUpdatePayload,
  type SeriesCreatePayload,
  type SeriesDto,
  type SeriesUpdatePayload,
  type StreamingStatusDto,
  type SystemPreflightDto,
  type SystemUpdateCheckDto,
  type SystemUpdateJobDto,
  type SystemVersionDto,
  type TmdbMediaType,
  type TmdbPreviewDto,
  type TmdbSearchResultDto,
  type CatalogListParams,
  type TmdbSearchResponseDto,
  type TmdbImportResponseDto,
  type TmdbRefreshResponseDto,
  type TmdbTitleRefreshResponseDto,
  type TmdbArtworkReplaceResponseDto,
  type UploadSessionCreatePayload,
  type ProcessingStatusDto,
  type ProcessingJobCreateResult,
  type EncodeJobCreateResult,
  type CustomerPlaybackSessionRequest,
  type CollectionPublicDto,
  type TokenResponse,
  type UploadSessionCreateResult,
  type UploadSessionDto,
} from './api';

function clearAdminAndNotify() {
  tokenStore.clearAdmin();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(ADMIN_UNAUTHORIZED_EVENT));
  }
}

const adminHttp = createHttp(() => tokenStore.getAdmin(), {
  onUnauthorized: clearAdminAndNotify,
});

export const adminApi = {
  async login(username: string, password: string) {
    const { data } = await adminHttp.post<TokenResponse>('/admin/auth/login', {
      username,
      password,
    });
    tokenStore.setAdmin(data.access_token);
    return data;
  },

  async me(): Promise<AdminUserDto> {
    const { data } = await adminHttp.get<AdminUserDto>('/admin/auth/me');
    return data;
  },

  async dashboardStats(): Promise<DashboardStatsDto> {
    const { data } = await adminHttp.get<DashboardStatsDto>('/admin/dashboard/stats');
    return data;
  },

  async getPublicationReadiness(entityType: CatalogEntityType, id: number) {
    const { data } = await adminHttp.get<PublicationReadinessDto>(
      `/admin/catalog/${entityType}/${id}/publication-readiness`
    );
    return data;
  },

  async getPublicationHistory(entityType: CatalogEntityType, id: number) {
    const { data } = await adminHttp.get<PublicationHistoryEventDto[]>(
      `/admin/catalog/${entityType}/${id}/publication-history`
    );
    return data;
  },

  async submitReview(entityType: CatalogEntityType, id: number, reason?: string) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/submit-review`,
      { reason }
    );
    return data;
  },

  async approve(entityType: CatalogEntityType, id: number, reason?: string) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/approve`,
      { reason }
    );
    return data;
  },

  async publish(entityType: CatalogEntityType, id: number, reason?: string) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/publish`,
      { reason }
    );
    return data;
  },

  async schedule(
    entityType: CatalogEntityType,
    id: number,
    scheduledPublishAt: string,
    reason?: string
  ) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/schedule`,
      { scheduled_publish_at: scheduledPublishAt, reason }
    );
    return data;
  },

  async unpublish(entityType: CatalogEntityType, id: number, reason?: string) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/unpublish`,
      { reason }
    );
    return data;
  },

  async archive(entityType: CatalogEntityType, id: number, reason?: string) {
    const { data } = await adminHttp.post<PublicationActionDto>(
      `/admin/catalog/${entityType}/${id}/archive`,
      { reason }
    );
    return data;
  },

  async listMovies(params?: CatalogListParams) {
    const { data } = await adminHttp.get<Envelope<MovieDto>>('/admin/movies', { params });
    return unwrapList(data);
  },

  async getMovie(id: number) {
    const { data } = await adminHttp.get<MovieDto>(`/admin/movies/${id}`);
    return data;
  },

  async createMovie(payload: MovieCreatePayload) {
    const { data } = await adminHttp.post<MovieDto>('/admin/movies', payload);
    return data;
  },

  async updateMovie(id: number, payload: MovieUpdatePayload) {
    const { data } = await adminHttp.patch<MovieDto>(`/admin/movies/${id}`, payload);
    return data;
  },

  async deleteMovie(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/movies/${id}`);
    return data;
  },

  async publishMovie(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/movies/${id}/publish`);
    return data;
  },

  async unpublishMovie(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/movies/${id}/unpublish`);
    return data;
  },

  async listSeries(params?: CatalogListParams) {
    const { data } = await adminHttp.get<Envelope<SeriesDto>>('/admin/series', { params });
    return unwrapList(data);
  },

  async getSeries(id: number) {
    const { data } = await adminHttp.get<SeriesDto>(`/admin/series/${id}`);
    return data;
  },

  async createSeries(payload: SeriesCreatePayload) {
    const { data } = await adminHttp.post<SeriesDto>('/admin/series', payload);
    return data;
  },

  async updateSeries(id: number, payload: SeriesUpdatePayload) {
    const { data } = await adminHttp.patch<SeriesDto>(`/admin/series/${id}`, payload);
    return data;
  },

  async deleteSeries(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/series/${id}`);
    return data;
  },

  async publishSeries(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/series/${id}/publish`);
    return data;
  },

  async unpublishSeries(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/series/${id}/unpublish`);
    return data;
  },

  async listSeasons(seriesId: number) {
    const { data } = await adminHttp.get<SeasonDto[]>(`/admin/series/${seriesId}/seasons`);
    return data;
  },

  async createSeason(seriesId: number, payload: SeasonCreatePayload) {
    const { data } = await adminHttp.post<SeasonDto>(`/admin/series/${seriesId}/seasons`, payload);
    return data;
  },

  async getSeason(id: number) {
    const { data } = await adminHttp.get<SeasonDto>(`/admin/seasons/${id}`);
    return data;
  },

  async updateSeason(id: number, payload: SeasonUpdatePayload) {
    const { data } = await adminHttp.patch<SeasonDto>(`/admin/seasons/${id}`, payload);
    return data;
  },

  async deleteSeason(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/seasons/${id}`);
    return data;
  },

  async listEpisodes(seasonId: number) {
    const { data } = await adminHttp.get<EpisodeDto[]>(`/admin/seasons/${seasonId}/episodes`);
    return data;
  },

  async createEpisode(seasonId: number, payload: EpisodeCreatePayload) {
    const { data } = await adminHttp.post<EpisodeDto>(`/admin/seasons/${seasonId}/episodes`, payload);
    return data;
  },

  async getEpisode(id: number) {
    const { data } = await adminHttp.get<EpisodeDto>(`/admin/episodes/${id}`);
    return data;
  },

  async updateEpisode(id: number, payload: EpisodeUpdatePayload) {
    const { data } = await adminHttp.patch<EpisodeDto>(`/admin/episodes/${id}`, payload);
    return data;
  },

  async deleteEpisode(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/episodes/${id}`);
    return data;
  },

  async publishEpisode(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/episodes/${id}/publish`);
    return data;
  },

  async unpublishEpisode(id: number) {
    const { data } = await adminHttp.post<{ detail: string; status: string }>(`/admin/episodes/${id}/unpublish`);
    return data;
  },

  async listGenres(params?: { q?: string; page?: number; page_size?: number }) {
    const { data } = await adminHttp.get<Envelope<GenreDto>>('/admin/genres', { params });
    return unwrapList(data);
  },

  async getGenre(id: number) {
    const { data } = await adminHttp.get<GenreDto>(`/admin/genres/${id}`);
    return data;
  },

  async createGenre(payload: GenreCreatePayload) {
    const { data } = await adminHttp.post<GenreDto>('/admin/genres', payload);
    return data;
  },

  async updateGenre(id: number, payload: GenreUpdatePayload) {
    const { data } = await adminHttp.patch<GenreDto>(`/admin/genres/${id}`, payload);
    return data;
  },

  async deleteGenre(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/genres/${id}`);
    return data;
  },

  async searchTmdb(params: { query: string; media_type: TmdbMediaType; page?: number }) {
    const { data } = await adminHttp.get<TmdbSearchResponseDto>('/admin/tools/tmdb/search', {
      params: {
        query: params.query,
        media_type: params.media_type,
        page: params.page ?? 1,
      },
    });
    return data;
  },

  async previewTmdb(payload: { tmdb_id: number; media_type: TmdbMediaType }) {
    const { data } = await adminHttp.post<TmdbPreviewDto>('/admin/tools/tmdb/preview', payload);
    return data;
  },

  async importTmdbDraft(payload: { tmdb_id: number; media_type: TmdbMediaType; force?: boolean }) {
    const { data } = await adminHttp.post<TmdbImportResponseDto>('/admin/tools/tmdb/import', {
      ...payload,
      force: payload.force ?? false,
    });
    return data;
  },

  async refreshTmdbDemo(payload?: { force?: boolean }) {
    const { data } = await adminHttp.post<TmdbRefreshResponseDto>('/admin/tools/tmdb/refresh', {
      force: payload?.force ?? false,
    });
    return data;
  },

  async refreshTmdbTitle(payload: { media_type: TmdbMediaType; entity_id: number }) {
    const { data } = await adminHttp.post<TmdbTitleRefreshResponseDto>(
      '/admin/tools/tmdb/refresh-title',
      payload
    );
    return data;
  },

  async refreshTmdbTranslations(payload: {
    media_type: TmdbMediaType;
    entity_id: number;
    include_episodes?: boolean;
  }) {
    const { data } = await adminHttp.post<{
      result: {
        entity_type: string;
        entity_id: number;
        tmdb_id: number | null;
        locales_written: string[];
        fields_written: number;
        skipped_manual: number;
        notes: string[];
      };
      item: MovieDto | SeriesDto | null;
    }>('/admin/tools/tmdb/refresh-translations', payload);
    return data;
  },

  async replaceTmdbArtwork(payload: {
    media_type: TmdbMediaType;
    entity_id: number;
    kinds: Array<'poster' | 'backdrop' | 'logo'>;
  }) {
    const { data } = await adminHttp.post<TmdbArtworkReplaceResponseDto>(
      '/admin/tools/tmdb/artwork/replace',
      payload
    );
    return data;
  },

  // Placeholder tooling endpoints (not wired in catalog admin UI)
  async listEncodingJobs() {
    const { data } = await adminHttp.get('/admin/encoding/jobs');
    return data;
  },

  async listUploads() {
    const { data } = await adminHttp.get('/admin/uploads');
    return data;
  },

  async createMediaUploadSession(payload: UploadSessionCreatePayload) {
    const { data } = await adminHttp.post<UploadSessionCreateResult>('/admin/media/sessions', payload);
    return data;
  },

  async uploadMediaSessionFile(
    sessionId: string,
    file: File,
    onUploadProgress?: (pct: number) => void,
    options?: { offset?: number; complete?: boolean }
  ) {
    const form = new FormData();
    form.append('file', file);
    const offset = options?.offset ?? 0;
    const complete = options?.complete ?? true;
    const { data } = await adminHttp.put<UploadSessionDto>(`/admin/media/sessions/${sessionId}`, form, {
      headers: {
        // Let the browser/axios set multipart boundary — do not force Content-Type.
        'Upload-Offset': String(offset),
        'Upload-Complete': complete ? 'true' : 'false',
      },
      timeout: 0,
      onUploadProgress: (event) => {
        if (!onUploadProgress || !event.total) return;
        onUploadProgress(Math.min(100, Math.round((event.loaded * 100) / event.total)));
      },
    });
    return data;
  },

  async getMediaUploadSession(sessionId: string) {
    const { data } = await adminHttp.get<UploadSessionDto>(`/admin/media/sessions/${sessionId}`);
    return data;
  },

  async cancelMediaUploadSession(sessionId: string) {
    const { data } = await adminHttp.delete<UploadSessionDto>(`/admin/media/sessions/${sessionId}`);
    return data;
  },

  async listMediaAssets(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    movie_id?: number;
    episode_id?: number;
    unassigned?: boolean;
    category?: string;
    q?: string;
    video_only?: boolean;
    linkable_only?: boolean;
  }) {
    const { data } = await adminHttp.get<Envelope<MediaAssetDto>>('/admin/media/assets', { params });
    return unwrapList(data);
  },

  async getMediaAsset(assetId: string) {
    const { data } = await adminHttp.get<MediaAssetDto>(`/admin/media/assets/${assetId}`);
    return data;
  },

  async linkMediaAsset(assetId: string, payload: { owner_type: 'movie' | 'episode'; owner_id: number }) {
    const { data } = await adminHttp.post<MediaAssetDto>(`/admin/media/assets/${assetId}/link`, payload);
    return data;
  },

  async attachExternalMedia(payload: {
    url: string;
    owner_type: 'movie' | 'episode';
    owner_id: number;
    category?: MediaCategory;
    acknowledge_unprotected_external: boolean;
  }) {
    const { data } = await adminHttp.post<MediaAssetDto>('/admin/media/external', payload);
    return data;
  },

  async detachMediaAsset(assetId: string, payload?: { force_unpublish?: boolean }) {
    const { data } = await adminHttp.post<MediaAssetDto>(
      `/admin/media/assets/${assetId}/detach`,
      payload ?? {}
    );
    return data;
  },

  async getMediaAssetUsages(assetId: string) {
    const { data } = await adminHttp.get<{ asset_id: string; usages: MediaAssetUsageDto[] }>(
      `/admin/media/assets/${assetId}/usages`
    );
    return data;
  },

  async deleteMediaAsset(assetId: string, confirm = true) {
    const { data } = await adminHttp.post<{
      id: string;
      deleted: boolean;
      removed_file: boolean;
      upload_status: string;
    }>(`/admin/media/assets/${assetId}/delete`, { confirm });
    return data;
  },

  async getMediaStorageHealth(params?: { include_orphans?: boolean }) {
    const { data } = await adminHttp.get<MediaStorageHealthDto>('/admin/media/storage-health', {
      params,
    });
    return data;
  },

  async cleanupStaleTempUploads(maxAgeSeconds = 86400) {
    const { data } = await adminHttp.post<{
      scanned: number;
      removed: number;
      max_age_seconds: number;
    }>('/admin/media/temp-cleanup', null, { params: { max_age_seconds: maxAgeSeconds } });
    return data;
  },

  async getProcessingStatus() {
    const { data } = await adminHttp.get<ProcessingStatusDto>('/admin/media/processing/status');
    return data;
  },

  async queueMediaProbe(assetId: string) {
    const { data } = await adminHttp.post<ProcessingJobCreateResult>(
      `/admin/media/assets/${assetId}/processing/probe`
    );
    return data;
  },

  async queueMediaEncodeHls(assetId: string) {
    const { data } = await adminHttp.post<EncodeJobCreateResult>(
      `/admin/media/assets/${assetId}/processing/encode-hls`
    );
    return data;
  },

  async listAssetProcessingJobs(assetId: string) {
    const { data } = await adminHttp.get<Envelope<ProcessingJobDto>>(
      `/admin/media/assets/${assetId}/processing`
    );
    return unwrapList(data);
  },

  async listAssetPackages(assetId: string) {
    const { data } = await adminHttp.get<Envelope<MediaPackageDto>>(
      `/admin/media/assets/${assetId}/packages`
    );
    return unwrapList(data);
  },

  async getMediaPackage(packageId: string) {
    const { data } = await adminHttp.get<MediaPackageDto>(`/admin/media/packages/${packageId}`);
    return data;
  },

  async listEncodingProfiles() {
    const { data } = await adminHttp.get<Envelope<EncodingProfileDto>>(
      '/admin/media/encoding/profiles'
    );
    return unwrapList(data);
  },

  async listProcessingJobs(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    job_type?: string;
    media_asset_id?: string;
  }) {
    const { data } = await adminHttp.get<Envelope<ProcessingJobDto>>('/admin/media/processing/jobs', {
      params,
    });
    return unwrapList(data);
  },

  async getProcessingJob(jobId: string) {
    const { data } = await adminHttp.get<ProcessingJobDto>(`/admin/media/processing/jobs/${jobId}`);
    return data;
  },

  async retryProcessingJob(jobId: string) {
    const { data } = await adminHttp.post<ProcessingJobDto>(
      `/admin/media/processing/jobs/${jobId}/retry`
    );
    return data;
  },

  async cancelProcessingJob(jobId: string) {
    const { data } = await adminHttp.delete<ProcessingJobDto>(
      `/admin/media/processing/jobs/${jobId}`
    );
    return data;
  },

  async getStreamingStatus() {
    const { data } = await adminHttp.get<StreamingStatusDto>('/streaming/status');
    return data;
  },

  async listPlaybackSessions(params?: {
    page?: number;
    page_size?: number;
    media_asset_id?: string;
    media_package_id?: string;
    principal_type?: string;
    principal_id?: string;
    status?: string;
  }) {
    const { data } = await adminHttp.get<Envelope<PlaybackSessionDto>>('/admin/playback/sessions', {
      params,
    });
    return unwrapList(data);
  },

  async createPlaybackSession(mediaAssetId: string) {
    const { data } = await adminHttp.post<PlaybackSessionCreatedDto>('/admin/playback/sessions', {
      media_asset_id: mediaAssetId,
    });
    return data;
  },

  /** Same /playback/sessions endpoint; sends admin JWT for ops tests. */
  async createPlayerPlaybackSession(body: CustomerPlaybackSessionRequest) {
    const { data } = await adminHttp.post<PlaybackSessionCreatedDto>('/playback/sessions', body);
    return data;
  },

  async revokePlaybackSession(sessionId: string) {
    const { data } = await adminHttp.post<PlaybackSessionDto>(
      `/admin/playback/sessions/${sessionId}/revoke`
    );
    return data;
  },

  async revokePlaybackSessionsForAsset(mediaAssetId: string) {
    const { data } = await adminHttp.post<{ revoked: number }>(
      '/admin/playback/sessions/revoke-asset',
      null,
      { params: { media_asset_id: mediaAssetId } }
    );
    return data;
  },

  async listCdnNodes() {
    const { data } = await adminHttp.get('/admin/cdn/nodes');
    return data;
  },

  async syncCdn(payload: {
    node_id?: number;
    content_type: string;
    content_id: number;
    hls_path: string;
  }) {
    const { data } = await adminHttp.post('/admin/cdn/sync', payload);
    return data;
  },

  async getSystemVersion() {
    const { data } = await adminHttp.get<SystemVersionDto>('/admin/system/version');
    return data;
  },

  async checkSystemUpdates() {
    const { data } = await adminHttp.post<SystemUpdateCheckDto>('/admin/system/updates/check');
    return data;
  },

  async runSystemUpdatePreflight() {
    const { data } = await adminHttp.post<SystemPreflightDto>('/admin/system/updates/preflight');
    return data;
  },

  async createSystemUpdateBackup(password: string) {
    const { data } = await adminHttp.post<{ backup_id: string; created_at?: string; validated: boolean }>(
      '/admin/system/updates/backup',
      { password, confirm: true }
    );
    return data;
  },

  async installSystemUpdate(payload: { password: string; confirm: boolean; target_version?: string }) {
    const { data } = await adminHttp.post<SystemUpdateJobDto>('/admin/system/updates/install', payload);
    return data;
  },

  async getSystemUpdateJob(jobId: string) {
    const { data } = await adminHttp.get<SystemUpdateJobDto>(`/admin/system/updates/${jobId}`);
    return data;
  },

  async rollbackSystemUpdate(
    jobId: string,
    payload: { password: string; confirm: boolean; confirm_database_restore?: boolean }
  ) {
    const { data } = await adminHttp.post<SystemUpdateJobDto>(
      `/admin/system/updates/${jobId}/rollback`,
      payload
    );
    return data;
  },

  async listSystemUpdateHistory(limit = 50) {
    const { data } = await adminHttp.get<{ items: SystemUpdateJobDto[]; total: number }>(
      '/admin/system/updates/history',
      { params: { limit } }
    );
    return data;
  },

  async listCollections(params?: AdminCollectionListParams) {
    const { data } = await adminHttp.get<Envelope<CollectionDto>>('/admin/collections', { params });
    return unwrapList(data);
  },

  async getCollection(id: number) {
    const { data } = await adminHttp.get<CollectionDto>(`/admin/collections/${id}`);
    return data;
  },

  async createCollection(payload: CollectionCreatePayload) {
    const { data } = await adminHttp.post<CollectionDto>('/admin/collections', payload);
    return data;
  },

  async updateCollection(id: number, payload: CollectionUpdatePayload) {
    const { data } = await adminHttp.patch<CollectionDto>(`/admin/collections/${id}`, payload);
    return data;
  },

  async deleteCollection(id: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(`/admin/collections/${id}`);
    return data;
  },

  async publishCollection(id: number, expectedUpdatedAt?: string | null) {
    const { data } = await adminHttp.post<CollectionDto>(
      `/admin/collections/${id}/publish`,
      expectedUpdatedAt ? { expected_updated_at: expectedUpdatedAt } : {}
    );
    return data;
  },

  async unpublishCollection(id: number, expectedUpdatedAt?: string | null) {
    const { data } = await adminHttp.post<CollectionDto>(
      `/admin/collections/${id}/unpublish`,
      expectedUpdatedAt ? { expected_updated_at: expectedUpdatedAt } : {}
    );
    return data;
  },

  async archiveCollection(id: number, expectedUpdatedAt?: string | null) {
    const { data } = await adminHttp.post<CollectionDto>(
      `/admin/collections/${id}/archive`,
      expectedUpdatedAt ? { expected_updated_at: expectedUpdatedAt } : {}
    );
    return data;
  },

  async previewCollection(id: number) {
    const { data } = await adminHttp.get<CollectionPublicDto>(`/admin/collections/${id}/preview`);
    return data;
  },

  async collectionPicker(params?: CollectionPickerParams) {
    const { data } = await adminHttp.get<CollectionPickerResultDto>('/admin/collections/picker', {
      params,
    });
    return data;
  },

  async addCollectionItem(id: number, payload: CollectionItemAddPayload) {
    const { data } = await adminHttp.post<CollectionItemDto>(`/admin/collections/${id}/items`, payload);
    return data;
  },

  async removeCollectionItem(id: number, itemId: number) {
    const { data } = await adminHttp.delete<{ detail: string }>(
      `/admin/collections/${id}/items/${itemId}`
    );
    return data;
  },

  async reorderCollectionItems(id: number, itemIds: number[], expectedUpdatedAt?: string | null) {
    const { data } = await adminHttp.put<CollectionDto>(`/admin/collections/${id}/items/reorder`, {
      item_ids: itemIds,
      expected_updated_at: expectedUpdatedAt ?? undefined,
    });
    return data;
  },

  async inspectRecommendations(subscriberId: number, limit = 20) {
    const { data } = await adminHttp.get<RecommendationInspectDto>('/admin/recommendations/inspect', {
      params: { subscriber_id: subscriberId, limit },
    });
    return data;
  },

  async listContentRequests(params?: {
    status?: string;
    request_type?: string;
    q?: string;
    page?: number;
    page_size?: number;
  }) {
    const { data } = await adminHttp.get<ContentRequestAdminListDto>('/admin/content-requests', {
      params,
    });
    return data;
  },

  async getContentRequest(id: number) {
    const { data } = await adminHttp.get<ContentRequestAdminDetailDto>(`/admin/content-requests/${id}`);
    return data;
  },

  async contentRequestAction(id: number, body: ContentRequestAdminActionBody) {
    const { data } = await adminHttp.post<ContentRequestDto>(
      `/admin/content-requests/${id}/actions`,
      body
    );
    return data;
  },

  async getPortalIntegration(): Promise<PortalIntegrationDto> {
    const { data } = await adminHttp.get<PortalIntegrationDto>('/admin/integrations/portal');
    return data;
  },

  async updatePortalIntegration(payload: PortalIntegrationUpdatePayload): Promise<PortalIntegrationDto> {
    const { data } = await adminHttp.put<PortalIntegrationDto>('/admin/integrations/portal', payload);
    return data;
  },

  async testPortalConnection(): Promise<PortalConnectionTestDto> {
    const { data } = await adminHttp.post<PortalConnectionTestDto>('/admin/integrations/portal/test');
    return data;
  },

  async getR2(): Promise<R2SettingsDto> { return (await adminHttp.get('/admin/cdn-management/r2')).data; },
  async updateR2(payload: R2SettingsPayload): Promise<R2SettingsDto> { return (await adminHttp.put('/admin/cdn-management/r2', payload)).data; },
  async listCDNNodes(): Promise<ManagedCDNNodeDto[]> { return (await adminHttp.get('/admin/cdn-management/nodes')).data; },
  async createCDNNode(payload: ManagedCDNNodePayload): Promise<ManagedCDNNodeCreatedDto> { return (await adminHttp.post('/admin/cdn-management/nodes', payload)).data; },
  async cdnNodeAction(id: string, action: string) { return (await adminHttp.post(`/admin/cdn-management/nodes/${id}/actions/${action}`, { confirm: true })).data; },
  async listCDNRoutes(): Promise<CDNPrefixRouteDto[]> { return (await adminHttp.get('/admin/cdn-management/routes')).data; },
  async createCDNRoute(payload: { cidr: string; node_id: string; priority: number; enabled: boolean }): Promise<CDNPrefixRouteDto> { return (await adminHttp.post('/admin/cdn-management/routes', payload)).data; },
};

export type R2SettingsDto = {
  enabled: boolean;
  endpoint_url: string;
  account_id?: string | null;
  bucket: string;
  region: string;
  public_base_url?: string;
  artwork_cdn_enabled?: boolean;
  credentials_configured: boolean;
  updated_at?: string | null;
};
export type R2SettingsPayload = {
  enabled: boolean;
  endpoint_url: string;
  account_id?: string;
  bucket: string;
  region: string;
  public_base_url?: string;
  artwork_cdn_enabled?: boolean;
  access_key_id?: string;
  secret_access_key?: string;
  remove_credentials?: boolean;
};
export type ManagedCDNNodeDto = { id: string; name: string; role: 'main'|'cache'; host: string; ssh_port: number; ssh_username: string; credential_type: string; credential_configured: boolean; branch?: string; location?: string; notes?: string; enabled: boolean; draining: boolean; is_default: boolean; cache_limit_bytes?: number; disk_total_bytes?: number; disk_free_bytes?: number; cached_objects: number; cached_titles: number; hit_rate?: number; bandwidth_bytes: number; rtt_ms?: number; software_version?: string; health_status: string; provision_status: string; last_sync_at?: string; last_heartbeat_at?: string };
export type ManagedCDNNodeCreatedDto = { node: ManagedCDNNodeDto; heartbeat_token: string | null };
export type ManagedCDNNodePayload = { name: string; role: 'main'|'cache'; host: string; ssh_port: number; ssh_username: string; credential_type: 'password'|'private_key'; credential: string; branch?: string; location?: string; notes?: string; enabled: boolean; is_default: boolean; cache_limit_bytes: number };
export type CDNPrefixRouteDto = { id: string; cidr: string; prefix_length: number; node_id: string; node_name?: string; priority: number; enabled: boolean };

export type PortalIntegrationDto = {
  enabled: boolean;
  base_url: string;
  api_prefix: string;
  client: string;
  request_source: string;
  connect_timeout_seconds: number;
  read_timeout_seconds: number;
  entitlement_ttl_seconds: number;
  token_configured: boolean;
  updated_at?: string | null;
  last_test_at?: string | null;
  last_test_ok?: boolean | null;
  last_test_http_status?: number | null;
  last_test_portal_reachable?: boolean | null;
  last_test_credential_accepted?: boolean | null;
  config_source?: string | null;
};

export type PortalIntegrationUpdatePayload = {
  enabled?: boolean;
  base_url?: string;
  api_prefix?: string;
  client?: string;
  request_source?: string;
  connect_timeout_seconds?: number;
  read_timeout_seconds?: number;
  entitlement_ttl_seconds?: number;
  token?: string;
  remove_token?: boolean;
};

export type PortalConnectionTestDto = {
  ok: boolean;
  portal_reachable: boolean;
  credential_accepted: boolean;
  http_status?: number | null;
  message: string;
};
