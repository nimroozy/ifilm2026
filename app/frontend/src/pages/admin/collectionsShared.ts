/** Shared constants/helpers for the Collections V1 admin UI (list + form pages). */

import { z } from 'zod';

export const COLLECTION_TYPES = [
  'editorial',
  'franchise',
  'seasonal',
  'genre_feature',
  'regional',
  'language',
  'staff_pick',
] as const;

export type CollectionTypeValue = (typeof COLLECTION_TYPES)[number];

export const COLLECTION_TYPE_LABELS: Record<string, string> = {
  editorial: 'Editorial',
  franchise: 'Franchise',
  seasonal: 'Seasonal',
  genre_feature: 'Genre Feature',
  regional: 'Regional',
  language: 'Language',
  staff_pick: 'Staff Pick',
};

export function collectionTypeLabel(value: string): string {
  return COLLECTION_TYPE_LABELS[value] || value;
}

function urlSchema(label: string) {
  return z
    .string()
    .optional()
    .refine((v) => !v || v.startsWith('http://') || v.startsWith('https://'), {
      message: `${label} must start with http:// or https://`,
    });
}

export const collectionFormSchema = z.object({
  title: z.string().min(1, 'Title is required'),
  slug: z.string().optional(),
  description: z.string().optional(),
  short_description: z.string().max(240, 'Keep short description under 240 characters').optional(),
  collection_type: z.enum(COLLECTION_TYPES),
  visibility: z.enum(['public', 'unlisted']),
  poster_url: urlSchema('Poster URL'),
  backdrop_url: urlSchema('Backdrop URL'),
  sort_order: z.coerce.number().int().optional().or(z.literal('')),
  is_featured: z.boolean().default(false),
});

export type CollectionFormValues = z.infer<typeof collectionFormSchema>;

/**
 * Allowed quick actions given the current status.
 * Mirrors backend transition rules: publish requires draft; unpublish always
 * resets to draft (including restoring from archived); archive is allowed
 * from any non-archived status.
 */
export function collectionStatusActions(status: string) {
  return {
    canPublish: status !== 'published' && status !== 'archived',
    canUnpublish: status === 'published',
    canRestore: status === 'archived',
    canArchive: status !== 'archived',
  };
}
