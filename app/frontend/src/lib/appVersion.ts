/** Customer-visible app version from build-time env (release images set VITE_APP_VERSION). */
export function getAppVersion(): string | null {
  const raw = (import.meta.env.VITE_APP_VERSION as string | undefined)?.trim();
  if (!raw || raw === 'undefined' || raw === 'null') return null;
  return raw.replace(/^v/i, '');
}
