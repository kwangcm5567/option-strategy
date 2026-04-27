import { useState, useEffect } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { apiFetch } from '../../hooks/useApi';
import { ErrorBox } from '../../components/ui/LoadingSpinner';
import Tooltip from '../../components/ui/Tooltip';
import { TIPS } from '../../constants/tooltips';

const STRATEGIES = [
  { value: 'sell_put',  label: '卖出 Put'  },
  { value: 'buy_call',  label: '买入 Call' },
  { value: 'sell_call', label: '卖出 Call' },
  { value: 'buy_put',   label: '买入 Put'  },
];

const today = () => new Date().toISOString().slice(0, 10);

const emptyForm = {
  symbol: '', strategy: 'sell_put', strike: '', premium: '',
  quantity: 1, expiration_date: '', open_date: today(), notes: '',
};

function DaysUntil({ dateStr }) {
  const days = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
  if (days < 0) return <span style={{ color: '#ef4444' }}>已到期</span>;
  if (days <= 7) return <span style={{ color: '#f59e0b' }}>{days} 天后到期 ⚠️</span>;
  return <span style={{ color: '#10b981' }}>{days} 天后到期</span>;
}

export default function PositionsTab() {
  const [positions, setPositions] = useState([]);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    try {
      const res = await apiFetch('GET', '/api/positions');
      setPositions(res.data || []);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => { load(); }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await apiFetch('POST', '/api/positions', {
        ...form,
        strike: parseFloat(form.strike),
        premium: parseFloat(form.premium),
        quantity: parseInt(form.quantity),
      });
      setForm(emptyForm);
      setShowForm(false);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('确定要删除这条持仓记录吗？')) return;
    try {
      await apiFetch('DELETE', `/api/positions/${id}`);
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  const inputStyle = {
    background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '8px', color: 'var(--text-primary)', padding: '0.45rem 0.7rem',
    fontSize: '0.85rem', width: '100%', outline: 'none',
  };

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.2rem' }}>持仓追踪</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>记录和追踪你的期权仓位，数据保存在本地数据库。</p>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            background: 'rgba(59,130,246,0.2)', border: '1px solid rgba(96,165,250,0.4)',
            color: '#60a5fa', padding: '0.5rem 1rem', borderRadius: '8px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600,
          }}
        >
          <Plus size={15} /> 新增持仓
        </button>
      </div>

      {error && <ErrorBox message={error} />}

      {/* 新增表单 */}
      {showForm && (
        <div className="glass-panel" style={{ padding: '1.25rem', marginBottom: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem', fontWeight: 700, fontSize: '0.95rem' }}>录入新仓位</h3>
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
              {[
                { label: '股票代码', field: 'symbol', type: 'text', placeholder: 'AAPL' },
                { label: '行权价 ($)', field: 'strike', type: 'number', placeholder: '200' },
                { label: '权利金 ($/股)', field: 'premium', type: 'number', placeholder: '2.50' },
                { label: '合约数量', field: 'quantity', type: 'number', placeholder: '1' },
                { label: '到期日', field: 'expiration_date', type: 'date' },
                { label: '开仓日', field: 'open_date', type: 'date' },
              ].map(({ label, field, type, placeholder }) => (
                <div key={field}>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>{label}</label>
                  <input
                    type={type}
                    value={form[field]}
                    onChange={e => setForm(p => ({ ...p, [field]: e.target.value }))}
                    placeholder={placeholder}
                    required={field !== 'notes'}
                    style={inputStyle}
                  />
                </div>
              ))}
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>策略类型</label>
                <select value={form.strategy} onChange={e => setForm(p => ({ ...p, strategy: e.target.value }))} style={inputStyle}>
                  {STRATEGIES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </div>
            </div>
            <div style={{ marginBottom: '0.75rem' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>备注（可选）</label>
              <input type="text" value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} placeholder="如：等待财报后波动率下降" style={{ ...inputStyle, width: '100%' }} />
            </div>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button type="submit" disabled={submitting} style={{ background: 'rgba(16,185,129,0.2)', border: '1px solid rgba(16,185,129,0.4)', color: '#10b981', padding: '0.5rem 1.25rem', borderRadius: '8px', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem' }}>
                {submitting ? '保存中…' : '✓ 保存'}
              </button>
              <button type="button" onClick={() => setShowForm(false)} style={{ background: 'none', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-secondary)', padding: '0.5rem 1rem', borderRadius: '8px', cursor: 'pointer', fontSize: '0.85rem' }}>
                取消
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 持仓列表 */}
      {positions.length === 0 ? (
        <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center' }}>
          <p style={{ color: 'var(--text-secondary)' }}>还没有任何持仓记录，点击「新增持仓」开始追踪。</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {positions.map(pos => {
            const isSell = pos.strategy.startsWith('sell_');
            const maxProfit = (pos.premium * pos.quantity * 100).toFixed(2);
            const maxLoss = isSell
              ? ((pos.strike - pos.premium) * pos.quantity * 100).toFixed(2)
              : (pos.premium * pos.quantity * 100).toFixed(2);
            const breakEven = isSell
              ? (pos.strategy === 'sell_put' ? pos.strike - pos.premium : pos.strike + pos.premium)
              : (pos.strategy === 'buy_call' ? pos.strike + pos.premium : pos.strike - pos.premium);
            const stratLabel = STRATEGIES.find(s => s.value === pos.strategy)?.label || pos.strategy;

            return (
              <div key={pos.id} className="glass-panel" style={{ padding: '1rem 1.25rem', display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center', flex: 1 }}>
                  <div>
                    <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>{pos.symbol}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2px' }}>{stratLabel}</div>
                  </div>
                  {[
                    { label: '行权价', value: `$${pos.strike.toFixed(2)}` },
                    { label: '开仓权利金', value: `$${pos.premium.toFixed(2)}/股` },
                    { label: '合约数', value: `${pos.quantity} 张` },
                    { label: '盈亏平衡', value: `$${breakEven.toFixed(2)}`, tip: TIPS.breakEven },
                    { label: '最大获利', value: `$${maxProfit}`, color: '#10b981', tip: TIPS.maxProfit },
                    { label: '最大亏损', value: isSell ? `$${maxLoss}` : `$${maxLoss}`, color: '#ef4444', tip: TIPS.maxLoss },
                    { label: '到期日', value: pos.expiration_date },
                  ].map(({ label, value, color, tip }) => (
                    <div key={label} style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>
                        {tip ? <Tooltip text={tip}><span>{label}</span></Tooltip> : label}
                      </div>
                      <div style={{ fontSize: '0.9rem', fontWeight: 600, color: color || 'var(--text-primary)' }}>{value}</div>
                    </div>
                  ))}
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>剩余时间</div>
                    <div style={{ fontSize: '0.85rem' }}><DaysUntil dateStr={pos.expiration_date} /></div>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(pos.id)}
                  style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444', padding: '0.4rem 0.7rem', borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.78rem' }}
                >
                  <Trash2 size={14} /> 删除
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
