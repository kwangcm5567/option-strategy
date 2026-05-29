import { useState } from 'react';
import { X } from 'lucide-react';

const SB_URL = import.meta.env.VITE_SUPABASE_URL ?? '';
const SB_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY ?? '';
const USE_CLOUD = !!(SB_URL && SB_KEY);

const sbHeaders = () => ({
  apikey: SB_KEY,
  Authorization: `Bearer ${SB_KEY}`,
  'Content-Type': 'application/json',
});

const LS_KEY = 'option_positions_v1';
const lsLoad = () => { try { return JSON.parse(localStorage.getItem(LS_KEY) ?? '[]'); } catch { return []; } };
const lsSave = (data) => localStorage.setItem(LS_KEY, JSON.stringify(data));

const todayStr = () => new Date().toISOString().slice(0, 10);

const STRATEGY_LABELS = {
  sell_put: '卖出 Put',
  buy_call: '买入 Call',
  sell_call: '卖出 Call',
  buy_put: '买入 Put',
};

export default function QuickAddModal({ option, onClose }) {
  const [form, setForm] = useState({
    symbol: option.symbol ?? '',
    strategy: option.strategy ?? 'sell_put',
    strike: option.strike != null ? String(option.strike) : '',
    premium: option.premium != null ? String(option.premium) : '',
    quantity: '1',
    expiration_date: option.expirationDate ?? '',
    open_date: todayStr(),
    notes: '',
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  // P2 — 财报日警告
  const earningsWarning = (() => {
    if (!option.earningsDate || !form.expiration_date) return null;
    const today = new Date();
    const earnings = new Date(option.earningsDate);
    const expiry = new Date(form.expiration_date);
    const daysToEarnings = Math.ceil((earnings - today) / 86400000);
    if (earnings <= expiry && daysToEarnings > 0 && daysToEarnings <= 14) {
      return `财报日 ${option.earningsDate} 在到期前 ${daysToEarnings} 天，IV Crush 风险极高！`;
    }
    return null;
  })();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    const posData = {
      symbol: form.symbol.toUpperCase(),
      strategy: form.strategy,
      strike: parseFloat(form.strike),
      premium: parseFloat(form.premium),
      quantity: parseInt(form.quantity),
      expiration_date: form.expiration_date,
      open_date: form.open_date,
      notes: form.notes,
    };

    try {
      if (USE_CLOUD) {
        const res = await fetch(`${SB_URL}/rest/v1/positions`, {
          method: 'POST',
          headers: { ...sbHeaders(), Prefer: 'return=minimal' },
          body: JSON.stringify(posData),
        });
        if (!res.ok) throw new Error(`Supabase ${res.status}`);
      } else {
        const existing = lsLoad();
        const updated = [...existing, { ...posData, id: Date.now() }]
          .sort((a, b) => a.expiration_date.localeCompare(b.expiration_date));
        lsSave(updated);
      }
      setSaved(true);
      setTimeout(onClose, 1200);
    } catch (e) {
      setError('保存失败：' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const inputStyle = {
    background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '8px', color: 'var(--text-primary)', padding: '0.45rem 0.7rem',
    fontSize: '0.85rem', width: '100%', outline: 'none',
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '1rem' }}
      onClick={onClose}
    >
      <div
        className="glass-panel"
        style={{ padding: '1.5rem', maxWidth: '480px', width: '100%', maxHeight: '90vh', overflowY: 'auto' }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ fontWeight: 700, fontSize: '1rem' }}>
            添加到持仓 — {option.symbol} {STRATEGY_LABELS[option.strategy]}
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        {/* P2 — 财报日警告 */}
        {earningsWarning && (
          <div style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.35)', borderRadius: '8px', padding: '0.65rem 0.85rem', marginBottom: '1rem', fontSize: '0.82rem', color: '#fca5a5' }}>
            ⚠️ {earningsWarning}
          </div>
        )}

        {saved ? (
          <div style={{ textAlign: 'center', padding: '1.5rem 0', color: '#10b981', fontSize: '1rem', fontWeight: 700 }}>
            ✅ 已成功添加到持仓！
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.65rem', marginBottom: '0.65rem' }}>
              {[
                { label: '股票代码', field: 'symbol', type: 'text' },
                { label: '行权价 ($)', field: 'strike', type: 'number' },
                { label: '权利金 ($/股)', field: 'premium', type: 'number' },
                { label: '合约数量', field: 'quantity', type: 'number' },
                { label: '到期日', field: 'expiration_date', type: 'date' },
                { label: '开仓日', field: 'open_date', type: 'date' },
              ].map(({ label, field, type }) => (
                <div key={field}>
                  <label style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '3px' }}>{label}</label>
                  <input
                    type={type}
                    value={form[field]}
                    onChange={e => setForm(p => ({ ...p, [field]: e.target.value }))}
                    required={field !== 'notes'}
                    style={inputStyle}
                  />
                </div>
              ))}
              <div>
                <label style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '3px' }}>策略</label>
                <select value={form.strategy} onChange={e => setForm(p => ({ ...p, strategy: e.target.value }))} style={inputStyle}>
                  {Object.entries(STRATEGY_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </div>
            </div>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '3px' }}>备注（可选）</label>
              <input
                type="text"
                value={form.notes}
                onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                placeholder="如：看好公司基本面，愿意持有"
                style={inputStyle}
              />
            </div>
            {error && (
              <div style={{ color: '#fca5a5', fontSize: '0.82rem', marginBottom: '0.75rem' }}>{error}</div>
            )}
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                type="submit"
                disabled={saving}
                style={{ flex: 1, background: 'rgba(16,185,129,0.2)', border: '1px solid rgba(16,185,129,0.4)', color: '#10b981', padding: '0.55rem', borderRadius: '8px', cursor: saving ? 'not-allowed' : 'pointer', fontWeight: 600, fontSize: '0.85rem' }}
              >
                {saving ? '保存中…' : '✓ 保存到持仓'}
              </button>
              <button
                type="button"
                onClick={onClose}
                style={{ background: 'none', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-secondary)', padding: '0.55rem 1rem', borderRadius: '8px', cursor: 'pointer', fontSize: '0.85rem' }}
              >
                取消
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
