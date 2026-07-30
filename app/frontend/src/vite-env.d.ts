/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DATA_MODE?: 'mock' | 'api' | string;
  readonly VITE_APP_TITLE?: string;
  readonly VITE_APP_DESCRIPTION?: string;
  readonly VITE_APP_LOGO_URL?: string;
  readonly VITE_SITE_URL?: string;
  readonly VITE_TWITTER_SITE?: string;
  readonly VITE_TWITTER_CREATOR?: string;
  readonly VITE_PORT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
