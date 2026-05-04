import { useState, useEffect, useRef } from 'react';
import { Plus, Trash2, TrendingUp, TrendingDown, X, ChevronDown, ChevronRight } from 'lucide-react';
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

const CLOSE_REASONS = [
  { value: 'profit_50', label: '50% 利润平仓（黄金法则）' },
  { value: 'expired',   label: '到期归零 / 行权' },
  { value: 'stop_loss', label: '止损平仓' },
  { value: 'manual',    label: '手动平仓（其他原因）' },
];

const today = () => new Date().toISOString().slice(0, 10);

const emptyForm = {
  symbol: '', strategy: 'sell_put', strike: '', premium: '',
  quantity: 1, expiration_date: '', open_date: today(), notes: '',
};

const SELL_STRATEGIES = new Set(['sell_put', 'sell_call']);

function pnlColor(v) {
  if (v > 0) return '#10b981';
  if (v < 0) return '#ef4444';
  return 'var(--text-secondary)';
}

function fmt$(v) {
  const abs = Math.abs(v).toFixed(2);
  return v >= 0 ? `+$${abs}` : `-$${abs}`;
}

function DaysUntil({ dateStr }) {
  const days = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
  if (days < 0) return <span style={{ color: '#ef4444' }}>已到期</span>;
  if (days <= 7) return <span style={{ color: '#f59e0b' }}>{days}天到期 ⚠️</span>;
  return <span style={{ color: '#10b981' }}>{days}天到期</span>;
}

// ── 压力测试计算 ─────────────────────────────────────────────────────────────

const SCENARIOS = [
  { label: '大跌 15%', spotChg: -0.15, ivChg: 0.50 },
  { label: '小跌 5%',  spotChg: -0.05, ivChg: 0.20 },
  { label: '平盘',     spotChg: 0,     ivChg: 0    },
  { label: '小涨 5%',  spotChg: 0.05,  ivChg: -0.10 },
  { label: '大涨 15%', spotChg: 0.15,  ivChg: -0.20 },
];

function calcScenarioPnl(pnlRows, spotChgPct, ivChgPct) {
  let total = 0;
  for (const row of pnlRows) {
    if (!row.delta || !row.currentPrice) continue;
    const dS = row.currentPrice * spotChgPct;
    const dPremium = row.delta * dS;
    total += dPremium * 100; // per contract
  }
  return total;
}

// ── 组合 Greeks 面板 ─────────────────────────────────────────────────────────

function GreeksPanel({ greeks }) {
  const [open, setOpen] = useState(true);
  if (!greeks) return null;
  const { totalDelta, dailyThetaIncome, totalVega, totalCapitalAtRisk, sellPutCount, buyCallCount } = greeks;

  return (
    <div className="glass-panel" style={{ padding: '1rem 1.25rem', marginBottom: '1rem' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-primary)', width: '100%', fontSize: '0.9rem', fontWeight: 700 }}
      >
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        📊 组合 Greeks 快照
        <span style={{ marginLeft: 'auto', fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
          {sellPutCount} 张卖 Put · {buyCallCount} 张买 Call
        </span>
      </button>
      {open && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.75rem', marginTop: '0.85rem' }}>
          {[
            {
              label: '净 Delta',
              value: totalDelta >= 0 ? `+${totalDelta.toFixed(3)}` : totalDelta.toFixed(3),
              color: totalDelta >= 0 ? '#10b981' : '#ef4444',
              hint: `大盘每涨 $1，组合盈亏约 ${totalDelta >= 0 ? '+' : ''}$${(totalDelta).toFixed(0)}`,
            },
            {
              label: '每日 Theta 收入',
              value: `+$${dailyThetaIncome.toFixed(2)}`,
              color: '#f59e0b',
              hint: '每天时间衰减带来的权利金收入（前提：股价不动）',
            },
            {
              label: '净 Vega 敞口',
              value: `$${totalVega.toFixed(2)}`,
              color: totalVega >= 0 ? '#10b981' : '#ef4444',
              hint: 'IV 每升 1%，组合盈亏变动金额（卖方为负）',
            },
            {
              label: '总占用保证金',
              value: `$${totalCapitalAtRisk.toLocaleString()}`,
              color: 'var(--text-primary)',
              hint: '卖 Put：行权价×100股；买 Call：权利金×100股',
            },
          ].map(({ label, value, color, hint }) => (
            <div key={label} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '0.65rem 0.85rem' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>{label}</div>
              <div style={{ fontSize: '1.05rem', fontWeight: 700, color }}>{value}</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '3px', lineHeight: 1.4 }}>{hint}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 汇总条 ───────────────────────────────────────────────────────────────────

function SummaryBar({ positions, pnlMap, closedPositions }) {
  const openPnl = positions.reduce((s, p) => s + (pnlMap[p.id]?.unrealizedPnl || 0), 0);
  const totalPremium = positions.reduce((s, p) => s + p.premium * p.quantity * 100, 0);
  const realizedTotal = closedPositions.reduce((s, p) => s + (p.realized_pnl || 0), 0);
  const wins = closedPositions.filter(p => (p.realized_pnl || 0) > 0).length;
  const winRate = closedPositions.length > 0 ? Math.round(wins / closedPositions.length * 100) : null;

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
      {[
        { label: '未实现盈亏', value: fmt$(openPnl), color: pnlColor(openPnl) },
        { label: '已收权利金', value: `$${totalPremium.toFixed(2)}`, color: '#f59e0b' },
        { label: '历史实现收益', value: fmt$(realizedTotal), color: pnlColor(realizedTotal) },
        ...(winRate !== null ? [{ label: `胜率（${closedPositions.length}笔）`, value: `${winRate}%`, color: winRate >= 60 ? '#10b981' : '#f59e0b' }] : []),
      ].map(({ label, value, color }) => (
        <div key={label} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '0.5rem 0.9rem', flex: '1 1 120px' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>{label}</div>
          <div style={{ fontSize: '0.95rem', fontWeight: 700, color }}>{value}</div>
        </div>
      ))}
    </div>
  );
}

// ── 压力测试面板 ─────────────────────────────────────────────────────────────

function StressPanel({ pnlData }) {
  const [open, setOpen] = useState(false);
  if (!pnlData || pnlData.length === 0) return null;

  return (
    <div className="glass-panel" style={{ padding: '1rem 1.25rem', marginTop: '1rem' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-primary)', width: '100%', fontSize: '0.9rem', fontWeight: 700 }}
      >
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        🧪 压力测试（Delta 近似）
      </button>
      {open && (
        <div style={{ marginTop: '0.85rem', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                {['场景', '价格变动', 'IV变动', '组合预估盈亏'].map(h => (
                  <th key={h} style={{ padding: '0.4rem 0.7rem', textAlign: 'left', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SCENARIOS.map(sc => {
                const pnl = calcScenarioPnl(pnlData, sc.spotChg, sc.ivChg);
                return (
                  <tr key={sc.label} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <td style={{ padding: '0.45rem 0.7rem', fontWeight: 600 }}>{sc.label}</td>
                    <td style={{ padding: '0.45rem 0.7rem', color: sc.spotChg < 0 ? '#ef4444' : sc.spotChg > 0 ? '#10b981' : 'var(--text-secondary)' }}>
                      {sc.spotChg >= 0 ? '+' : ''}{(sc.spotChg * 100).toFixed(0)}%
                    </td>
                    <td style={{ padding: '0.45rem 0.7rem', color: 'var(--text-secondary)' }}>
                      {sc.ivChg >= 0 ? '+' : ''}{(sc.ivChg * 100).toFixed(0)}%
                    </td>
                    <td style={{ padding: '0.45rem 0.7rem', fontWeight: 700, color: pnlColor(pnl) }}>
                      {fmt$(pnl)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
            * 基于 Delta 线性近似，实际盈亏因 Gamma / Vega 影响会有偏差
          </p>
        </div>
      )}
    </div>
  );
}

// ── 平仓对话框 ───────────────────────────────────────────────────────────────

function CloseDialog({ pos, onClose, onConfirm }) {
  const [exitPremium, setExitPremium] = useState('');
  const [reason, setReason] = useState('profit_50');
  const [submitting, setSubmitting] = useState(false);

  const isSell = SELL_STRATEGIES.has(pos.strategy);
  const preview = exitPremium
    ? isSell
      ? (pos.premium - parseFloat(exitPremium)) * pos.quantity * 100
      : (parseFloat(exitPremium) - pos.premium) * pos.quantity * 100
    : null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await onConfirm({ exit_premium: parseFloat(exitPremium), exit_date: today(), close_reason: reason });
    } finally {
      setSubmitting(false);
    }
  };

  const inputStyle = {
    background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.2)',
    borderRadius: '8px', color: 'var(--text-primary)', padding: '0.45rem 0.7rem',
    fontSize: '0.85rem', width: '100%', outline: 'none',
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="glass-panel" style={{ padding: '1.5rem', width: '380px', maxWidth: '95vw' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ fontWeight: 700 }}>平仓 {pos.symbol} {STRATEGIES.find(s => s.value === pos.strategy)?.label}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}><X size={18} /></button>
        </div>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          开仓权利金：${pos.premium.toFixed(2)}/股 · {pos.quantity} 张合约
        </p>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>平仓价格（买回/卖出价格，$/股）</label>
            <input
              type="number" step="0.01" min="0" required
              value={exitPremium}
              onChange={e => setExitPremium(e.target.value)}
              placeholder={isSell ? '买回价格（越低越好）' : '卖出价格（越高越好）'}
              style={inputStyle}
            />
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>平仓原因</label>
            <select value={reason} onChange={e => setReason(e.target.value)} style={inputStyle}>
              {CLOSE_REASONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </div>
          {preview !== null && (
            <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: '8px', padding: '0.6rem 0.85rem', marginBottom: '0.85rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>预计实现盈亏</span>
              <span style={{ fontWeight: 700, fontSize: '1rem', color: pnlColor(preview) }}>{fmt$(preview)}</span>
            </div>
          )}
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button type="submit" disabled={submitting} style={{ flex: 1, background: 'rgba(16,185,129,0.2)', border: '1px solid rgba(16,185,129,0.4)', color: '#10b981', padding: '0.5rem', borderRadius: '8px', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem' }}>
              {submitting ? '记录中…' : '✓ 确认平仓'}
            </button>
            <button type="button" onClick={onClose} style={{ background: 'none', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-secondary)', padding: '0.5rem 1rem', borderRadius: '8px', cursor: 'pointer', fontSize: '0.85rem' }}>
              取消
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── 持仓卡片 ─────────────────────────────────────────────────────────────────

function PositionCard({ pos, pnl, onDelete, onClose }) {
  const isSell = SELL_STRATEGIES.has(pos.strategy);
  const maxProfit = (pos.premium * pos.quantity * 100).toFixed(2);
  const maxLoss = isSell
    ? ((pos.strike - pos.premium) * pos.quantity * 100).toFixed(2)
    : (pos.premium * pos.quantity * 100).toFixed(2);
  const breakEven = isSell
    ? (pos.strategy === 'sell_put' ? pos.strike - pos.premium : pos.strike + pos.premium)
    : (pos.strategy === 'buy_call' ? pos.strike + pos.premium : pos.strike - pos.premium);
  const stratLabel = STRATEGIES.find(s => s.value === pos.strategy)?.label || pos.strategy;

  const show50Alert = isSell && pnl?.profitProgress >= 50;

  return (
    <div className="glass-panel" style={{ padding: '1rem 1.25rem', position: 'relative' }}>
      {/* 50% 利润提醒横幅 */}
      {show50Alert && (
        <div style={{ background: 'rgba(245,158,11,0.15)', border: '1px solid rgba(245,158,11,0.4)', borderRadius: '8px', padding: '0.4rem 0.75rem', marginBottom: '0.75rem', fontSize: '0.8rem', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          ⚡ 已达最大利润 {pnl.profitProgress.toFixed(0)}%，可考虑提前平仓锁定收益（50% 黄金法则）
        </div>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center', flex: 1 }}>
          {/* 标的 + 策略 */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '1.2rem', fontWeight: 700 }}>{pos.symbol}</span>
              {pnl && !pnl.error && (
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: pnlColor(pnl.unrealizedPnl) }}>
                  {pnl.unrealizedPnl >= 0 ? <TrendingUp size={13} style={{ display: 'inline', marginRight: 2 }} /> : <TrendingDown size={13} style={{ display: 'inline', marginRight: 2 }} />}
                  {fmt$(pnl.unrealizedPnl)} ({pnl.unrealizedPnlPct >= 0 ? '+' : ''}{pnl.unrealizedPnlPct}%)
                </span>
              )}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2px' }}>{stratLabel}</div>
            {pnl?.currentPrice && (
              <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                现价 ${pnl.currentPrice}
              </div>
            )}
          </div>

          {/* 核心数据格 */}
          {[
            { label: '行权价', value: `$${pos.strike.toFixed(2)}` },
            { label: '开仓权利金', value: `$${pos.premium.toFixed(2)}/股` },
            { label: '合约数', value: `${pos.quantity} 张` },
            { label: '盈亏平衡', value: `$${breakEven.toFixed(2)}`, tip: TIPS.breakEven },
            { label: '最大获利', value: `$${maxProfit}`, color: '#10b981', tip: TIPS.maxProfit },
            { label: '最大亏损', value: `$${maxLoss}`, color: '#ef4444', tip: TIPS.maxLoss },
            { label: '到期日', value: pos.expiration_date },
          ].map(({ label, value, color, tip }) => (
            <div key={label} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>
                {tip ? <Tooltip text={tip}><span>{label}</span></Tooltip> : label}
              </div>
              <div style={{ fontSize: '0.9rem', fontWeight: 600, color: color || 'var(--text-primary)' }}>{value}</div>
            </div>
          ))}

          {/* Theta / Delta (live) */}
          {pnl && !pnl.error && (
            <>
              {pnl.theta != null && (
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>每日 Theta</div>
                  <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f59e0b' }}>
                    {isSell ? '+' : ''}{(Math.abs(pnl.theta) * pos.quantity * 100).toFixed(2)}/天
                  </div>
                </div>
              )}
            </>
          )}

          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>剩余时间</div>
            <div style={{ fontSize: '0.85rem' }}><DaysUntil dateStr={pos.expiration_date} /></div>
          </div>
        </div>

        {/* 操作按钮 */}
        <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
          <button
            onClick={() => onClose(pos)}
            style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.3)', color: '#10b981', padding: '0.4rem 0.7rem', borderRadius: '8px', cursor: 'pointer', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
          >
            平仓
          </button>
          <button
            onClick={() => onDelete(pos.id)}
            style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444', padding: '0.4rem 0.7rem', borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.78rem' }}
          >
            <Trash2 size={14} /> 删除
          </button>
        </div>
      </div>

      {/* 利润进度条（仅卖方） */}
      {isSell && pnl?.profitProgress != null && (
        <div style={{ marginTop: '0.75rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            <span>利润进度</span>
            <span style={{ color: pnl.profitProgress >= 50 ? '#f59e0b' : '#10b981' }}>{pnl.profitProgress.toFixed(0)}% / 100%</span>
          </div>
          <div style={{ height: '5px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: '3px',
              width: `${Math.min(100, Math.max(0, pnl.profitProgress))}%`,
              background: pnl.profitProgress >= 50 ? 'linear-gradient(90deg,#f59e0b,#fbbf24)' : 'linear-gradient(90deg,#10b981,#34d399)',
              transition: 'width 0.5s ease',
            }} />
          </div>
        </div>
      )}

      {pos.notes && (
        <div style={{ marginTop: '0.6rem', fontSize: '0.75rem', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
          📝 {pos.notes}
        </div>
      )}
    </div>
  );
}

// ── 已平仓记录 ───────────────────────────────────────────────────────────────

function ClosedSection({ positions }) {
  const [open, setOpen] = useState(false);
  if (positions.length === 0) return null;

  const thisMonth = new Date().toISOString().slice(0, 7);
  const monthPnl = positions
    .filter(p => (p.exit_date || '').startsWith(thisMonth))
    .reduce((s, p) => s + (p.realized_pnl || 0), 0);

  return (
    <div className="glass-panel" style={{ padding: '1rem 1.25rem', marginTop: '1rem' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-primary)', width: '100%', fontSize: '0.9rem', fontWeight: 700 }}
      >
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        📋 已平仓记录（{positions.length} 笔）
        <span style={{ marginLeft: 'auto', fontSize: '0.78rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
          本月：<span style={{ color: pnlColor(monthPnl), fontWeight: 600 }}>{fmt$(monthPnl)}</span>
        </span>
      </button>
      {open && (
        <div style={{ marginTop: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {positions.map(pos => {
            const stratLabel = STRATEGIES.find(s => s.value === pos.strategy)?.label || pos.strategy;
            const reasonLabel = CLOSE_REASONS.find(r => r.value === pos.close_reason)?.label || pos.close_reason || '手动';
            return (
              <div key={pos.id} style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', padding: '0.6rem 0.75rem', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', fontSize: '0.82rem' }}>
                <span style={{ fontWeight: 700, minWidth: 50 }}>{pos.symbol}</span>
                <span style={{ color: 'var(--text-secondary)' }}>{stratLabel}</span>
                <span>开仓 ${pos.premium.toFixed(2)} → 平仓 ${(pos.exit_premium || 0).toFixed(2)}</span>
                <span style={{ color: 'var(--text-secondary)' }}>{pos.exit_date}</span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{reasonLabel}</span>
                <span style={{ marginLeft: 'auto', fontWeight: 700, color: pnlColor(pos.realized_pnl || 0) }}>
                  {fmt$(pos.realized_pnl || 0)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── 主组件 ───────────────────────────────────────────────────────────────────

export default function PositionsTab() {
  const [allPositions, setAllPositions] = useState([]);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [pnlMap, setPnlMap] = useState({});
  const [greeks, setGreeks] = useState(null);
  const [pnlLoading, setPnlLoading] = useState(false);
  const [closingPos, setClosingPos] = useState(null);
  const pnlTimerRef = useRef(null);

  const openPositions = allPositions.filter(p => p.status === 'open' || !p.status);
  const closedPositions = allPositions.filter(p => p.status === 'closed');

  const load = async () => {
    try {
      const res = await apiFetch('GET', '/api/positions');
      setAllPositions(res.data || []);
    } catch (e) {
      setError(e.message);
    }
  };

  const loadPnl = async () => {
    if (pnlLoading) return;
    setPnlLoading(true);
    try {
      const [pnlRes, greeksRes] = await Promise.all([
        apiFetch('GET', '/api/portfolio/pnl'),
        apiFetch('GET', '/api/portfolio/greeks'),
      ]);
      const map = {};
      for (const row of (pnlRes.data || [])) map[row.id] = row;
      setPnlMap(map);
      setGreeks(greeksRes.data || null);
    } catch {
      // PnL 获取失败不阻断主界面
    } finally {
      setPnlLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (openPositions.length === 0) return;
    loadPnl();
    pnlTimerRef.current = setInterval(loadPnl, 120_000);
    return () => clearInterval(pnlTimerRef.current);
  }, [openPositions.length]);

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

  const handleCloseConfirm = async ({ exit_premium, exit_date, close_reason }) => {
    try {
      await apiFetch('POST', `/api/positions/${closingPos.id}/close`, { exit_premium, exit_date, close_reason });
      setClosingPos(null);
      await load();
      await loadPnl();
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
      {/* 标题栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.2rem' }}>持仓追踪</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            实时盈亏 · 平仓记录 · Greeks 监控
            {pnlLoading && <span style={{ marginLeft: '0.5rem', fontSize: '0.75rem', color: '#60a5fa' }}>⟳ 刷新中…</span>}
          </p>
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

      {/* 汇总条 */}
      {allPositions.length > 0 && (
        <SummaryBar positions={openPositions} pnlMap={pnlMap} closedPositions={closedPositions} />
      )}

      {/* Greeks 面板 */}
      {greeks && openPositions.length > 0 && <GreeksPanel greeks={greeks} />}

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
      {openPositions.length === 0 && closedPositions.length === 0 ? (
        <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center' }}>
          <p style={{ color: 'var(--text-secondary)' }}>还没有任何持仓记录，点击「新增持仓」开始追踪。</p>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {openPositions.map(pos => (
              <PositionCard
                key={pos.id}
                pos={pos}
                pnl={pnlMap[pos.id]}
                onDelete={handleDelete}
                onClose={setClosingPos}
              />
            ))}
          </div>

          {/* 压力测试 */}
          <StressPanel pnlData={Object.values(pnlMap)} />

          {/* 已平仓记录 */}
          <ClosedSection positions={closedPositions} />
        </>
      )}

      {/* 平仓对话框 */}
      {closingPos && (
        <CloseDialog
          pos={closingPos}
          onClose={() => setClosingPos(null)}
          onConfirm={handleCloseConfirm}
        />
      )}
    </div>
  );
}
