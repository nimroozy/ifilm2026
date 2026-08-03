export interface RuntimeConfig {
  API_BASE_URL: string;
  ENABLE_WATCH_HISTORY?: boolean;
  WATCH_PROGRESS_MIN_SECONDS?: number;
  WATCH_PROGRESS_COMPLETE_PERCENT?: number;
  WATCH_PROGRESS_SAVE_INTERVAL_SECONDS?: number;
  WATCH_PROGRESS_RESUME_MARGIN_SECONDS?: number;
}

// Runtime configuration
let runtimeConfig: RuntimeConfig | null = null;

// Configuration loading state
let configLoading = true;

// Same-origin default — never point production browsers at localhost.
const defaultConfig: RuntimeConfig = {
  API_BASE_URL: '',
  ENABLE_WATCH_HISTORY: true,
  WATCH_PROGRESS_MIN_SECONDS: 30,
  WATCH_PROGRESS_COMPLETE_PERCENT: 90,
  WATCH_PROGRESS_SAVE_INTERVAL_SECONDS: 20,
  WATCH_PROGRESS_RESUME_MARGIN_SECONDS: 10,
};

const debugConfig = (...args: unknown[]) => {
  if (import.meta.env.DEV) {
    console.debug(...args);
  }
};

// Function to load runtime configuration
export async function loadRuntimeConfig(): Promise<void> {
  try {
    debugConfig('Starting to load runtime config...');
    // Try to load configuration from a config endpoint
    const response = await fetch('/api/config');
    if (response.ok) {
      const contentType = response.headers.get('content-type');
      // Only parse as JSON if the response is actually JSON
      if (contentType && contentType.includes('application/json')) {
        runtimeConfig = await response.json();
        debugConfig('Runtime config loaded successfully');
      } else {
        debugConfig(
          'Config endpoint returned non-JSON response, skipping runtime config'
        );
      }
    } else {
      debugConfig('Config fetch failed with status:', response.status);
    }
  } catch (error) {
    debugConfig('Failed to load runtime config, using defaults:', error);
  } finally {
    configLoading = false;
    debugConfig('Config loading finished');
  }
}

// Get current configuration
export function getConfig(): RuntimeConfig {
  // If config is still loading, return default config to avoid using stale Vite env vars
  if (configLoading) {
    return defaultConfig;
  }

  // First try runtime config (for Lambda)
  if (runtimeConfig) {
    return runtimeConfig;
  }

  // Then try Vite environment variables (for local development)
  if (import.meta.env.VITE_API_BASE_URL) {
    return {
      API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
    };
  }

  // Finally fall back to default
  return defaultConfig;
}

// Dynamic API_BASE_URL getter - this will always return the current config
export function getAPIBaseURL(): string {
  const baseURL = getConfig().API_BASE_URL;
  // If the base URL is just '/', return empty string to avoid double slashes and incorrect http:// prefix
  if (baseURL === '/') {
    return '';
  }
  return baseURL;
}

// For backward compatibility, but this should be avoided
// Removed static export to prevent using stale config values
// export const API_BASE_URL = getAPIBaseURL();

export const config = {
  get API_BASE_URL() {
    return getAPIBaseURL();
  },
};
