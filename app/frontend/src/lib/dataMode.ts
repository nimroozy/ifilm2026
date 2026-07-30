export type DataMode = 'mock' | 'api';

export function getDataMode(): DataMode {
  const raw = (import.meta.env.VITE_DATA_MODE as string | undefined)?.trim().toLowerCase();
  return raw === 'api' ? 'api' : 'mock';
}

export function isApiMode(): boolean {
  return getDataMode() === 'api';
}

export function isMockMode(): boolean {
  return getDataMode() === 'mock';
}
