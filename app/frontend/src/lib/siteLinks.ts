/**
 * External links shown in the customer footer.
 * Only include verified real destinations — never invent social or app-store URLs.
 */
export type SiteExternalLink = {
  id: string;
  href: string;
  labelKey: 'website' | 'facebook';
};

export const MOBIN_NET_WEBSITE = 'https://mobinnet.af/';
export const MOBIN_NET_FACEBOOK = 'https://www.facebook.com/mobinnetict';
export const MOBIN_NET_SUPPORT_EMAIL = 'support@mobinnet.af';
export const TMDB_WEBSITE = 'https://www.themoviedb.org/';

/** Real social / partner links only. No app-store badges. */
export const FOOTER_SOCIAL_LINKS: SiteExternalLink[] = [
  { id: 'website', href: MOBIN_NET_WEBSITE, labelKey: 'website' },
  { id: 'facebook', href: MOBIN_NET_FACEBOOK, labelKey: 'facebook' },
];
