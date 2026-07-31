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

// Default fallback configuration
const defaultConfig: RuntimeConfig = {
  API_BASE_URL: 'http://127.0.0.1:8000', // Only used if runtime config fails to load
  ENABLE_WATCH_HISTORY: true,
  WATCH_PROGRESS_MIN_SECONDS: 30,
  WATCH_PROGRESS_COMPLETE_PERCENT: 90,
  WATCH_PROGRESS_SAVE_INTERVAL_SECONDS: 20,
  WATCH_PROGRESS_RESUME_MARGIN_SECONDS: 10,
};

// Function to load runtime configuration
export async function loadRuntimeConfig(): Promise<void> {
  try {
    console.log('🔧 DEBUG: Starting to load runtime config...');
    // Try to load configuration from a config endpoint
    const response = await fetch('/api/config');
    if (response.ok) {
      const contentType = response.headers.get('content-type');
      // Only parse as JSON if the response is actually JSON
      if (contentType && contentType.includes('application/json')) {
        runtimeConfig = await response.json();
        console.log('Runtime config loaded successfully');
      } else {
        console.log(
          'Config endpoint returned non-JSON response, skipping runtime config'
        );
      }
    } else {
      console.log(
        '🔧 DEBUG: Config fetch failed with status:',
        response.status
      );
    }
  } catch (error) {
    console.log('Failed to load runtime config, using defaults:', error);
  } finally {
    configLoading = false;
    console.log(
      '🔧 DEBUG: Config loading finished, configLoading set to false'
    );
  }
}

// Get current configuration
export function getConfig(): RuntimeConfig {
  // If config is still loading, return default config to avoid using stale Vite env vars
  if (configLoading) {
    console.log('Config still loading, using default config');
    return defaultConfig;
  }

  // First try runtime config (for Lambda)
  if (runtimeConfig) {
    console.log('Using runtime config');
    return runtimeConfig;
  }

  // Then try Vite environment variables (for local development)
  if (import.meta.env.VITE_API_BASE_URL) {
    const viteConfig = {
      API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
    };
    console.log('Using Vite environment config');
    return viteConfig;
  }

  // Finally fall back to default
  console.log('Using default config');
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
