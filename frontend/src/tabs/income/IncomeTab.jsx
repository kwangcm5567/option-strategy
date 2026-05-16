import { useState } from 'react';
import { Target, RefreshCw } from 'lucide-react';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine, Cell,
} from 'recharts';
import { useApi } from '../../hooks/useApi';
import { ErrorBox } from '../../components/ui/LoadingSpinner';

const STRAT_LABELS = {
  sell_put:  '卖出 Put',
  buy_call:  '买入 Call',
  sell_call: '卖出 Call',
  buy_put:   '买入 Put',
};

const LS_GOAL_KEY = 'alpha_monthly_income_goal';

function fmt$(v, sign = false) {
  const abs = Math.abs(v).toFixed(0);
  const prefix = sign ? (v >= 0 ? '+$' : '-$') : (v < 0 ? '-$' : '$');
  return `${prefix}${Number(abs).toLocaleString()}`;
}

// ── 月度收入柱状图 ────────────────────────────────────────────────────────────

function MonthlyTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={{ background: 'rgba(15,23,42,0.95)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '0.75rem 1rem', fontSize: '0.82rem' }}>
      <div style={{ fontWeight: 700, marginBottom: '0.4rem' }}>{label}</div>
      <div style={{ color: d.totalPnl >= 0 ? '#10b981' : '#ef4444' }}>盈亏：{fmt$(d.totalPnl, true)}</div>
      <div style={{ color: '#f59e0b' }}>收权利金：{fmt$(d.premiumCollected)}</div>
      <div style={{ color: 'var(--text-secondary)' }}>交易 {d.tradeCount} 笔 · 胜率 {d.winRate}%</div>
      {d.profitFactor && <div style={{ color: '#a78bfa' }}>利润因子：{d.profitFactor}</div>}
    </div>
  );
}

function MonthlyBarChart({ data, goal }) {
  if (!data?.length) {
    return (
      <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
        暂无已平仓记录。平仓持仓后此处将显示月度收入走势。
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-secondary)' }} />
        <YAxis tick={{ fontSize: 11, fill: 'var(--text-secondary)' }} tickFormatter={v => `$${v}`} />
        <Tooltip content={<MonthlyTooltip />} />
        {goal > 0 && (
          <ReferenceLine y={goal} stroke="#f59e0b" strokeDasharray="6 3"
            label={{ value: `目标 $${goal}`, fill: '#f59e0b', fontSize: 11, position: 'insideTopRight' }} />
        )}
        <Bar dataKey="totalPnl" radius={[4, 4, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.totalPnl >= 0 ? '#10b981' : '#ef4444'} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── 目标设置 ──────────────────────────────────────────────────────────────────

function GoalSetter({ goal, onChange }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(String(goal));

  const save = () => {
    const n = parseFloat(val);
    if (!isNaN(n) && n >= 0) onChange(n);
    setEditing(false);
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
      <Target size={14} style={{ color: '#f59e0b' }} />
      <span style={{ color: 'var(--text-secondary)' }}>月度目标：</span>
      {editing ? (
        <>
          <input
            autoFocus value={val} onChange={e => setVal(e.target.value)}
            onBlur={save} onKeyDown={e => e.key === 'Enter' && save()}
            style={{ width: 80, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: 6, color: 'var(--text-primary)', padding: '0.2rem 0.4rem', fontSize: '0.85rem', textAlign: 'right' }}
          />
          <span style={{ color: 'var(--text-secondary)' }}>$/月</span>
        </>
      ) : (
        <button
          onClick={() => setEditing(true)}
          style={{ color: '#f59e0b', fontWeight: 700, background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.85rem', padding: 0 }}
        >
          {goal > 0 ? `$${goal.toLocaleString()}/月` : '点击设置目标 →'}
        </button>
      )}
    </div>
  );
}

// ── 策略绩效表 ────────────────────────────────────────────────────────────────

function PerformanceTable({ byStrategy, bySymbol }) {
  const [view, setView] = useState('strategy');

  const rows = view === 'strategy'
    ? byStrategy.map(r => ({ key: STRAT_LABELS[r.strategy] ?? r.strategy, ...r }))
    : bySymbol.map(r => ({ key: r.symbol, ...r }));

  if (!rows.length) return null;

  const pfColor = pf => pf >= 2 ? '#10b981' : pf >= 1.5 ? '#f59e0b' : pf >= 1 ? '#f97316' : '#ef4444';

  return (
    <div>
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
        {['strategy', 'symbol'].map(v => (
          <button key={v} onClick={() => setView(v)}
            style={{
              padding: '0.3rem 0.8rem', borderRadius: '999px', fontSize: '0.78rem', cursor: 'pointer',
              border: `1px solid ${view === v ? 'rgba(96,165,250,0.5)' : 'rgba(255,255,255,0.1)'}`,
              background: view === v ? 'rgba(59,130,246,0.15)' : 'transparent',
              color: view === v ? '#60a5fa' : 'var(--text-secondary)',
            }}
          >{v === 'strategy' ? '按策略' : '按标的'}</button>
        ))}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
              <th style={{ textAlign: 'left', padding: '0.4rem 0.5rem' }}>{view === 'strategy' ? '策略' : '标的'}</th>
              <th style={{ textAlign: 'right', padding: '0.4rem 0.5rem' }}>交易数</th>
              <th style={{ textAlign: 'right', padding: '0.4rem 0.5rem' }}>胜率</th>
              <th style={{ textAlign: 'right', padding: '0.4rem 0.5rem' }}>总盈亏</th>
              {view === 'strategy' && <th style={{ textAlign: 'right', padding: '0.4rem 0.5rem' }}>平均盈</th>}
              {view === 'strategy' && <th style={{ textAlign: 'right', padding: '0.4rem 0.5rem' }}>平均亏</th>}
              <th style={{ textAlign: 'right', padding: '0.4rem 0.5rem' }}>利润因子</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <td style={{ padding: '0.45rem 0.5rem', fontWeight: 600 }}>{r.key}</td>
                <td style={{ textAlign: 'right', padding: '0.45rem 0.5rem', color: 'var(--text-secondary)' }}>{r.trades}</td>
                <td style={{ textAlign: 'right', padding: '0.45rem 0.5rem', color: r.winRate >= 70 ? '#10b981' : r.winRate >= 50 ? '#f59e0b' : '#ef4444' }}>
                  {r.winRate}%
                </td>
                <td style={{ textAlign: 'right', padding: '0.45rem 0.5rem', fontWeight: 600, color: r.totalPnl >= 0 ? '#10b981' : '#ef4444' }}>
                  {fmt$(r.totalPnl, true)}
                </td>
                {view === 'strategy' && (
                  <td style={{ textAlign: 'right', padding: '0.45rem 0.5rem', color: '#10b981' }}>
                    {r.avgWin > 0 ? fmt$(r.avgWin) : '—'}
                  </td>
                )}
                {view === 'strategy' && (
                  <td style={{ textAlign: 'right', padding: '0.45rem 0.5rem', color: '#ef4444' }}>
                    {r.avgLoss < 0 ? fmt$(r.avgLoss) : '—'}
                  </td>
                )}
                <td style={{ textAlign: 'right', padding: '0.45rem 0.5rem', color: r.profitFactor ? pfColor(r.profitFactor) : 'var(--text-secondary)', fontWeight: 600 }}>
                  {r.profitFactor ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Wheel 循环追踪 ────────────────────────────────────────────────────────────

function WheelCycles({ cycles }) {
  if (!cycles?.length) return null;

  const statusColor = s => s === 'active' ? '#10b981' : s === 'assigned' ? '#f59e0b' : '#60a5fa';
  const statusLabel = s => s === 'active' ? '进行中' : s === 'assigned' ? '已被行权→持股' : '已完成';
  const stratLabel = s => STRAT_LABELS[s] ?? s;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {cycles.map(cycle => (
        <div key={cycle.cycleId} className="glass-panel" style={{ padding: '0.9rem 1.1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span style={{ fontWeight: 700, fontSize: '1rem' }}>{cycle.symbol}</span>
              <span style={{ fontSize: '0.72rem', padding: '0.15rem 0.5rem', borderRadius: '999px',
                background: `${statusColor(cycle.status)}20`, color: statusColor(cycle.status), border: `1px solid ${statusColor(cycle.status)}40` }}>
                {statusLabel(cycle.status)}
              </span>
            </div>
            <span style={{ fontWeight: 700, color: cycle.totalPremium >= 0 ? '#10b981' : '#ef4444', fontSize: '0.95rem' }}>
              累计 {fmt$(cycle.totalPremium, true)}
            </span>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {cycle.legs.map((leg, i) => (
              <div key={leg.id} style={{
                background: 'rgba(255,255,255,0.04)', borderRadius: 8, padding: '0.4rem 0.7rem',
                fontSize: '0.75rem', borderLeft: `3px solid ${leg.status === 'open' ? '#60a5fa' : '#10b98180'}`,
              }}>
                <div style={{ fontWeight: 600, color: '#60a5fa' }}>第 {i + 1} 腿：{stratLabel(leg.strategy)}</div>
                <div style={{ color: 'var(--text-secondary)' }}>行权价 ${leg.strike} · {leg.quantity}张</div>
                <div style={{ color: leg.status === 'open' ? '#f59e0b' : 'var(--text-secondary)' }}>
                  {leg.status === 'open' ? `到期：${leg.expirationDate}` : `已平仓 ${leg.exitDate ?? ''}`}
                </div>
                {leg.realizedPnl != null && (
                  <div style={{ color: leg.realizedPnl >= 0 ? '#10b981' : '#ef4444', fontWeight: 600 }}>
                    {fmt$(leg.realizedPnl, true)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

export default function IncomeTab() {
  const [goal, setGoal] = useState(() => parseFloat(localStorage.getItem(LS_GOAL_KEY) || '0'));
  const [activeSection, setActiveSection] = useState('income');

  const { data: monthlyData, error: mError, refetch: mRefetch } = useApi('/api/analytics/monthly');
  const { data: perfData,   error: pError }                    = useApi('/api/analytics/performance');
  const { data: wheelData,  loading: wLoading }                = useApi('/api/analytics/wheel-cycles');

  const saveGoal = (v) => {
    setGoal(v);
    localStorage.setItem(LS_GOAL_KEY, String(v));
  };

  const monthly    = monthlyData?.data ?? [];
  const summary    = perfData?.summary ?? {};
  const byStrategy = perfData?.byStrategy ?? [];
  const bySymbol   = perfData?.bySymbol ?? [];
  const cycles     = wheelData?.data ?? [];

  // 当月进度
  const now = new Date();
  const thisMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const currentMonthData = monthly.find(m => m.month === thisMonth);
  const currentMonthPnl = currentMonthData?.totalPnl ?? 0;
  const goalPct = goal > 0 ? Math.min(Math.round(currentMonthPnl / goal * 100), 150) : 0;

  // 年初至今
  const thisYear = String(now.getFullYear());
  const ytdPnl = monthly.filter(m => m.month?.startsWith(thisYear)).reduce((s, m) => s + m.totalPnl, 0);

  // 年化运行率（近 3 个月平均 × 12）
  const recent3 = monthly.slice(-3);
  const avgMonthly = recent3.length ? recent3.reduce((s, m) => s + m.totalPnl, 0) / recent3.length : 0;
  const annualRunRate = Math.round(avgMonthly * 12);

  const SECTIONS = [
    { id: 'income',  label: '月度收入' },
    { id: 'perf',    label: '绩效归因' },
    { id: 'wheel',   label: `Wheel 追踪${cycles.length ? ` (${cycles.length})` : ''}` },
  ];

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      {/* 标题 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.2rem' }}>被动收入中心</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>月度盈亏 · 策略归因 · Wheel 循环追踪</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <GoalSetter goal={goal} onChange={saveGoal} />
          <button onClick={() => mRefetch()}
            style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-secondary)', padding: '0.35rem 0.7rem', borderRadius: 8, cursor: 'pointer', fontSize: '0.8rem' }}>
            <RefreshCw size={13} /> 刷新
          </button>
        </div>
      </div>

      {/* KPI 汇总卡 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '0.75rem', marginBottom: '1.25rem' }}>
        {[
          { label: '本月实现盈亏', value: fmt$(currentMonthPnl, true), color: currentMonthPnl >= 0 ? '#10b981' : '#ef4444',
            sub: goal > 0 ? `目标完成 ${goalPct}%` : '未设目标' },
          { label: '年初至今（YTD）', value: fmt$(ytdPnl, true), color: ytdPnl >= 0 ? '#10b981' : '#ef4444',
            sub: `${thisYear} 年累计` },
          { label: '年化运行率', value: `$${Math.abs(annualRunRate).toLocaleString()}/年`,
            color: annualRunRate > 0 ? '#f59e0b' : 'var(--text-secondary)', sub: '近 3 月均值 × 12' },
          { label: '历史总交易', value: summary.totalTrades ?? 0,
            color: 'var(--text-primary)', sub: `胜率 ${summary.overallWinRate ?? 0}%` },
          { label: '总实现盈亏', value: fmt$(summary.totalPnl ?? 0, true),
            color: (summary.totalPnl ?? 0) >= 0 ? '#10b981' : '#ef4444', sub: '所有已平仓' },
          { label: '总利润因子', value: summary.profitFactor ?? '—',
            color: (summary.profitFactor ?? 0) >= 1.5 ? '#10b981' : '#f59e0b', sub: '≥1.5 为优质系统' },
        ].map(({ label, value, color, sub }) => (
          <div key={label} className="glass-panel" style={{ padding: '0.85rem 1rem' }}>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>{label}</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 700, color }}>{value}</div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', marginTop: '3px' }}>{sub}</div>
          </div>
        ))}
      </div>

      {/* 本月目标进度条 */}
      {goal > 0 && (
        <div className="glass-panel" style={{ padding: '0.75rem 1.1rem', marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '6px' }}>
            <span>本月进度</span>
            <span style={{ color: goalPct >= 100 ? '#10b981' : '#f59e0b' }}>
              {fmt$(currentMonthPnl)} / ${goal.toLocaleString()} = {goalPct}%
            </span>
          </div>
          <div style={{ height: 8, background: 'rgba(255,255,255,0.08)', borderRadius: 4, overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 4, transition: 'width 0.8s ease',
              width: `${Math.min(goalPct, 100)}%`,
              background: goalPct >= 100 ? '#10b981' : goalPct >= 60 ? '#f59e0b' : '#60a5fa',
            }} />
          </div>
        </div>
      )}

      {/* Section 切换 */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        {SECTIONS.map(s => (
          <button key={s.id} onClick={() => setActiveSection(s.id)}
            style={{
              padding: '0.35rem 0.9rem', borderRadius: '999px', cursor: 'pointer', fontSize: '0.82rem',
              border: `1px solid ${activeSection === s.id ? 'rgba(96,165,250,0.5)' : 'rgba(255,255,255,0.1)'}`,
              background: activeSection === s.id ? 'rgba(59,130,246,0.15)' : 'transparent',
              color: activeSection === s.id ? '#60a5fa' : 'var(--text-secondary)',
            }}>{s.label}</button>
        ))}
      </div>

      {/* 月度收入区 */}
      {activeSection === 'income' && (
        <div className="glass-panel" style={{ padding: '1.1rem 1.25rem' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '1rem', color: 'var(--text-secondary)' }}>
            月度已实现盈亏（绿色=盈利，红色=亏损）
          </h3>
          {mError ? <ErrorBox message={mError} /> : <MonthlyBarChart data={monthly} goal={goal} />}
          {monthly.length > 0 && (
            <div style={{ marginTop: '1rem', display: 'flex', flexWrap: 'wrap', gap: '1.25rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              <span>📅 共 {monthly.length} 个月数据</span>
              <span>✅ 盈利月份：{monthly.filter(m => m.totalPnl > 0).length} 个</span>
              <span>❌ 亏损月份：{monthly.filter(m => m.totalPnl < 0).length} 个</span>
              <span>💰 最佳月份：{fmt$(Math.max(...monthly.map(m => m.totalPnl)), true)}</span>
            </div>
          )}
        </div>
      )}

      {/* 绩效归因区 */}
      {activeSection === 'perf' && (
        <div className="glass-panel" style={{ padding: '1.1rem 1.25rem' }}>
          <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '1rem', color: 'var(--text-secondary)' }}>
            策略 / 标的绩效归因
          </h3>
          {pError ? <ErrorBox message={pError} /> : (
            <>
              {byStrategy.length === 0 && bySymbol.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                  暂无已平仓数据。平仓持仓后此处将显示绩效分析。
                </div>
              ) : (
                <PerformanceTable byStrategy={byStrategy} bySymbol={bySymbol} />
              )}
            </>
          )}
        </div>
      )}

      {/* Wheel 追踪区 */}
      {activeSection === 'wheel' && (
        <div>
          <div className="glass-panel" style={{ padding: '0.75rem 1.1rem', marginBottom: '1rem', fontSize: '0.83rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <strong style={{ color: 'var(--text-primary)' }}>Wheel 策略说明：</strong>
            卖出 Put → 被行权买入股票 → 卖出 Covered Call → 被 Call 走/到期 → 重新卖 Put。
            在持仓追踪页平仓 Put 时选择"行权"原因，再开一张 CC 时选择同一 Wheel 循环 ID，即可在此追踪完整周期。
          </div>
          {wLoading ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)' }}>加载中…</div>
          ) : cycles.length === 0 ? (
            <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              暂无 Wheel 循环记录。在平仓时选择"行权"，然后新开 CC 时关联循环 ID。
            </div>
          ) : (
            <WheelCycles cycles={cycles} />
          )}
        </div>
      )}
    </div>
  );
}
