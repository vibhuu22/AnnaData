import { t } from '../Config/uiLanguage';
import { useEffect, useState } from 'react';

export default function AppStatus() {
  const [offline, setOffline] = useState(!navigator.onLine);
  const [installPrompt, setInstallPrompt] = useState(null);
  useEffect(() => {
    const online = () => setOffline(false);
    const offline = () => setOffline(true);
    const install = (event) => { event.preventDefault(); setInstallPrompt(event); };
    const installed = () => setInstallPrompt(null);
    window.addEventListener('online', online);
    window.addEventListener('offline', offline);
    window.addEventListener('beforeinstallprompt', install);
    window.addEventListener('appinstalled', installed);
    return () => {
      window.removeEventListener('online', online);
      window.removeEventListener('offline', offline);
      window.removeEventListener('beforeinstallprompt', install);
      window.removeEventListener('appinstalled', installed);
    };
  }, []);
  if (offline) return <p role="status" className="shrink-0 bg-grain-50 px-4 py-2 text-center text-sm text-soil-800">{t("You’re offline. Reconnect to send a question or sign in.")}</p>;
  if (!installPrompt) return null;
  return <button className="min-h-touch shrink-0 bg-leaf-50 px-4 py-2 text-sm font-semibold text-leaf-800" onClick={async () => {
    const prompt = installPrompt;
    setInstallPrompt(null);
    try { await prompt.prompt(); } catch { /* Browser installation remains available. */ }
  }}>{t("Add AnnaData to your home screen")}</button>;
}
