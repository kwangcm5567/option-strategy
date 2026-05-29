import { useEffect } from 'react';

const LS_KEY = 'option_positions_v1';
const NOTIFIED_KEY = 'alpha_expiry_notified_date';

export default function useExpiryReminder() {
  useEffect(() => {
    if (!('Notification' in window)) return;

    const check = async () => {
      const today = new Date().toISOString().slice(0, 10);
      if (localStorage.getItem(NOTIFIED_KEY) === today) return;

      let permission = Notification.permission;
      if (permission === 'default') {
        permission = await Notification.requestPermission();
      }
      if (permission !== 'granted') return;

      try {
        const positions = JSON.parse(localStorage.getItem(LS_KEY) ?? '[]');
        const now = new Date();
        const soonExpiring = positions.filter(p => {
          if (p.status === 'closed') return false;
          const dte = Math.ceil((new Date(p.expiration_date) - now) / 86400000);
          return dte >= 0 && dte <= 3;
        });

        if (soonExpiring.length === 0) return;

        localStorage.setItem(NOTIFIED_KEY, today);
        new Notification('⏰ Alpha Options — 持仓即将到期', {
          body: soonExpiring.map(p =>
            `${p.symbol} $${p.strike} 到期日：${p.expiration_date}`
          ).join('\n'),
          icon: '/favicon.svg',
          tag: 'expiry-reminder',
          requireInteraction: true,
        });
      } catch { /* ignore */ }
    };

    check();
    const id = setInterval(check, 3_600_000);
    return () => clearInterval(id);
  }, []);
}
