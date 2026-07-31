import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ADMIN_UNAUTHORIZED_EVENT, adminApi, ApiError, tokenStore } from '@/lib/api';
import { LoadingBlock } from './adminShared';

interface RequireAdminProps {
  children: React.ReactNode;
}

export default function RequireAdmin({ children }: RequireAdminProps) {
  const location = useLocation();
  const [state, setState] = useState<'loading' | 'ok' | 'deny'>('loading');

  useEffect(() => {
    let cancelled = false;

    async function verify() {
      const token = tokenStore.getAdmin();
      if (!token) {
        if (!cancelled) setState('deny');
        return;
      }
      try {
        const me = await adminApi.me();
        if (cancelled) return;
        // Reject inactive or missing admin identity
        if (!me?.is_active || !me.username) {
          tokenStore.clearAdmin();
          setState('deny');
          return;
        }
        setState('ok');
      } catch (err) {
        if (cancelled) return;
        const apiErr = err instanceof ApiError ? err : null;
        // Only 401 clears the session. 403 is authorization failure, not logout.
        if (apiErr?.status === 401) {
          tokenStore.clearAdmin();
        }
        setState('deny');
      }
    }

    verify();

    const onUnauthorized = () => {
      setState('deny');
    };
    window.addEventListener(ADMIN_UNAUTHORIZED_EVENT, onUnauthorized);
    return () => {
      cancelled = true;
      window.removeEventListener(ADMIN_UNAUTHORIZED_EVENT, onUnauthorized);
    };
  }, [location.pathname]);

  if (state === 'loading') {
    return (
      <div className="min-h-screen bg-background p-8">
        <LoadingBlock rows={4} />
      </div>
    );
  }

  if (state === 'deny') {
    return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
