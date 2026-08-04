import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useLang } from '@/components/CustomerLayout';
import { applyDocumentLocale } from '@/lib/locale';

/**
 * Owns documentElement lang/dir.
 * Admin routes always force LTR English document attributes so portaled
 * dialogs/drawers stay LTR. Public routes follow the customer language.
 * Never writes to storage and never overwrites the saved public locale.
 */
export default function DocumentLangSync() {
  const { pathname } = useLocation();
  const { lang } = useLang();

  useEffect(() => {
    applyDocumentLocale(lang, pathname);
    document.documentElement.classList.add('dark');
  }, [pathname, lang]);

  return null;
}
