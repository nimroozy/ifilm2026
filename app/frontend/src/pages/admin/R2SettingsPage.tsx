import { Navigate } from 'react-router-dom';

/** Legacy path — Storage / CDN is the single settings page. */
export default function R2SettingsPage() {
  return <Navigate to="/admin/settings/storage" replace />;
}
