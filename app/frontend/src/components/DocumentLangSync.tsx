import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useLang } from '@/components/CustomerLayout';

/**
 * Owns documentElement lang/dir.
 * Admin routes always force LTR English document attributes so portaled
 * dialogs/drawers stay LTR. Public routes follow the customer language.
 */
export default function DocumentLangSync() {
  const { pathname } = useLocation();
  const { lang, dir } = useLang();
  const isAdminRoute = pathname === '/admin' || pathname.startsWith('/admin/');

  useEffect(() => {
    if (isAdminRoute) {
      document.documentElement.setAttribute('dir', 'ltr');
      document.documentElement.setAttribute('lang', 'en');
    } else {
      document.documentElement.setAttribute('dir', dir);
      document.documentElement.setAttribute('lang', lang);
    }
    document.documentElement.classList.add('dark');
  }, [isAdminRoute, dir, lang]);

  return null;
}
