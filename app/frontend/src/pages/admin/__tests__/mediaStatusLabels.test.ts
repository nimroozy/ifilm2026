import { describe, expect, it } from 'vitest';
import { mediaAssetStatusLabels } from '../MediaLinkingCard';
import type { MediaAssetDto, MediaPackageDto } from '@/lib/api';

function asset(partial: Partial<MediaAssetDto>): MediaAssetDto {
  return {
    id: 'a1',
    original_filename: 'film.mp4',
    mime_type: 'video/mp4',
    extension: 'mp4',
    size_bytes: 1,
    category: 'originals',
    upload_status: 'completed',
    processing_status: 'ready',
    storage_backend: 'local',
    ...partial,
  } as MediaAssetDto;
}

describe('mediaAssetStatusLabels', () => {
  it('labels validated external media', () => {
    const labels = mediaAssetStatusLabels(
      asset({
        source_type: 'external',
        external_url: 'https://cdn.example/a.mp4',
        external_validated_at: '2026-01-01T00:00:00Z',
      }),
      []
    );
    expect(labels).toContain('External Validated');
    expect(labels).toContain('Ready');
    expect(labels).not.toContain('Not Playable');
  });

  it('labels package ready uploaded media', () => {
    const pkgs = [
      { id: 'p1', is_active: true, status: 'completed' } as MediaPackageDto,
    ];
    const labels = mediaAssetStatusLabels(asset({}), pkgs);
    expect(labels).toContain('Package Ready');
    expect(labels).toContain('Ready');
  });

  it('labels not playable without package', () => {
    const labels = mediaAssetStatusLabels(asset({}), []);
    expect(labels).toContain('Not Playable');
  });
});
