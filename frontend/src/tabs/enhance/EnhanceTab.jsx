import { useState } from 'react';
import { apiFetch } from '../../hooks/useApi';
import { ErrorBox } from '../../components/ui/LoadingSpinner';

function pct(v) {
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function dollar(v) {
  return `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const inputStyle = {
  background: 'rgba(255,255,255,0.06)',
  border: '1px solid rgba(255,255,255,0.15)',
  borderRadius: '8px',
  color: 'var(--text-primary)',
  padding: '0.45rem 0.7rem',
  fontSize: '0.85rem',
  outline: 'none',
  width: '100%',
};

function MetricCell({ label, value, color, hint }) {
  return (
    <div style={{ textAlign: 'center', padding: '0.5rem 0.25rem' }}>
      <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', marginBottom: '3px' }}>{label}</div>
      <div style={{ fontSize: '0.9rem', fontWeight: 700, color: color || 'var(--text-primary)' }}>{value}</div>
      {hint && <div style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', marginTop: '2px', lineHeight: 1.3 }}>{hint}</div>}
    </div>
  );
}

// ── Covered Call 结果表 ─────────────────────────────────────────────────────

function CoveredCallTable({ data, shares }) {
  const contracts = Math.max(1, Math.floor(shares / 100));
  return (
    <div style={{ overflowX: 'auto', marginTop: '1rem' }}>
      {data.suggestions.length === 0 ? (
        <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>
          未找到合适的 Covered Call 选项（可能期权链数据不足）
        </p>
      ) : (
        <>
          <div style={{ marginBottom: '0.75rem', padding: '0.65rem 1rem', background: 'rgba(59,130,246,0.08)', borderRadius: '8px', borderLeft: '3px solid rgba(59,130,246,0.5)', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            <strong style={{ color: 'var(--text-primary)' }}>{data.symbol}</strong> 当前价 <strong>${data.currentPrice}</strong>
            {data.costBasis > 0 && <span> · 持仓成本 <strong>${data.costBasis}</strong></span>}
            {' '}· {contracts} 张合约（{shares} 股）· 历史波动率 {data.histVolatility}%
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.12)' }}>
                {['到期日', 'DTE', '行权价', '距现价', '权利金/股', '合约收入', '年化收益率', '被行权总收益', 'Delta', '成交量'].map(h => (
                  <th key={h} style={{ padding: '0.4rem 0.6rem', textAlign: 'right', color: 'var(--text-secondary)', fontWeight: 600, whiteSpace: 'nowrap', fontSize: '0.72rem' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.suggestions.map((s, i) => {
                const annRet = data.costBasis > 0 ? s.annualizedReturnOnCost : s.annualizedReturnOnPrice;
                const retColor = annRet >= 20 ? '#10b981' : annRet >= 10 ? '#f59e0b' : 'var(--text-primary)';
                return (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', background: i % 2 === 0 ? 'rgba(255,255,255,0.015)' : 'transparent' }}>
                    <td style={{ padding: '0.45rem 0.6rem', whiteSpace: 'nowrap' }}>{s.expirationDate}</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: 'var(--text-secondary)' }}>{s.dte}天</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', fontWeight: 600 }}>${s.strike}</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: '#10b981' }}>+{s.otmPct.toFixed(1)}%</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: '#f59e0b', fontWeight: 600 }}>${s.premium.toFixed(2)}</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: '#f59e0b' }}>${s.totalPremiumIncome}</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', fontWeight: 700, color: retColor }}>
                      {annRet != null ? `${annRet.toFixed(1)}%` : '—'}
                    </td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: '#10b981' }}>
                      {dollar(s.totalReturnIfCalled)}
                      <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', display: 'block' }}>({pct(s.totalReturnIfCalledPct)})</span>
                    </td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: 'var(--text-secondary)' }}>
                      {s.delta != null ? s.delta.toFixed(2) : '—'}
                    </td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: 'var(--text-secondary)' }}>{s.volume}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
            年化收益率 = 权利金 / {data.costBasis > 0 ? '持仓成本' : '当前价格'} / DTE × 365。被行权总收益 = 资本增值 + 权利金（基于{data.costBasis > 0 ? '持仓成本' : '当前价格'}）。
          </p>
        </>
      )}
    </div>
  );
}

// ── Protective Put 结果表 ──────────────────────────────────────────────────

function ProtectivePutTable({ data, shares }) {
  return (
    <div style={{ overflowX: 'auto', marginTop: '1rem' }}>
      {data.suggestions.length === 0 ? (
        <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>
          未找到合适的 Protective Put 选项
        </p>
      ) : (
        <>
          <div style={{ marginBottom: '0.75rem', padding: '0.65rem 1rem', background: 'rgba(239,68,68,0.08)', borderRadius: '8px', borderLeft: '3px solid rgba(239,68,68,0.4)', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            <strong style={{ color: 'var(--text-primary)' }}>{data.symbol}</strong> 当前价 <strong>${data.currentPrice}</strong>
            {' '}· {shares} 股总市值 <strong>${(data.currentPrice * shares).toLocaleString()}</strong> · 历史波动率 {data.histVolatility}%
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.12)' }}>
                {['到期日', 'DTE', '行权价', '保护水位', '权利金/股', '总保险费', '年化成本', 'Put 盈亏平衡', '最大亏损', 'Delta'].map(h => (
                  <th key={h} style={{ padding: '0.4rem 0.6rem', textAlign: 'right', color: 'var(--text-secondary)', fontWeight: 600, whiteSpace: 'nowrap', fontSize: '0.72rem' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.suggestions.map((s, i) => {
                const costColor = s.annualizedCostPct <= 3 ? '#10b981' : s.annualizedCostPct <= 6 ? '#f59e0b' : '#ef4444';
                return (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', background: i % 2 === 0 ? 'rgba(255,255,255,0.015)' : 'transparent' }}>
                    <td style={{ padding: '0.45rem 0.6rem', whiteSpace: 'nowrap' }}>{s.expirationDate}</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: 'var(--text-secondary)' }}>{s.dte}天</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', fontWeight: 600 }}>${s.strike}</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right' }}>
                      <span style={{ color: '#ef4444' }}>跌至 {s.protectionFloorPct}%</span>
                      <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', display: 'block' }}>(-{s.otmPct.toFixed(1)}%)</span>
                    </td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: '#ef4444', fontWeight: 600 }}>${s.premium.toFixed(2)}</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: '#ef4444' }}>${s.totalCost}</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', fontWeight: 700, color: costColor }}>
                      {s.annualizedCostPct.toFixed(1)}%/年
                    </td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: 'var(--text-secondary)' }}>${s.putBreakEven}</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: '#f59e0b' }}>${s.protectedMaxLoss.toLocaleString()}</td>
                    <td style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: 'var(--text-secondary)' }}>
                      {s.delta != null ? s.delta.toFixed(2) : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
            年化成本 = 权利金 / 现价 / DTE × 365。最大亏损 = (现价-行权价) × 股数 + 权利金成本（含 Put 对冲后的最坏情况）。
          </p>
        </>
      )}
    </div>
  );
}

// ── 知识卡片 ─────────────────────────────────────────────────────────────────

function KnowledgeCard({ title, items, color }) {
  return (
    <div style={{ background: `rgba(${color},0.06)`, border: `1px solid rgba(${color},0.2)`, borderRadius: '10px', padding: '1rem 1.25rem' }}>
      <h4 style={{ fontWeight: 700, marginBottom: '0.6rem', fontSize: '0.9rem' }}>{title}</h4>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        {items.map((item, i) => (
          <li key={i} style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            <span style={{ color: `rgb(${color})`, marginRight: '0.4rem' }}>▸</span>{item}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── 主组件 ───────────────────────────────────────────────────────────────────

export default function EnhanceTab() {
  const [mode, setMode] = useState('covered_call');

  // 共用输入
  const [symbol, setSymbol] = useState('');
  const [shares, setShares] = useState('100');
  const [costBasis, setCostBasis] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!symbol.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const params = new URLSearchParams({ shares: shares || '100' });
      if (costBasis && parseFloat(costBasis) > 0) params.set('cost_basis', costBasis);
      const endpoint = mode === 'covered_call'
        ? `/api/covered-call/${symbol.trim().toUpperCase()}?${params}`
        : `/api/protective-put/${symbol.trim().toUpperCase()}?${params}`;
      const data = await apiFetch('GET', endpoint);
      setResult({ mode, data });
    } catch (err) {
      setError(err.message || '请求失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.25rem' }}>组合增强</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          用期权加强现有股票仓位：卖出 Covered Call 收取权利金 · 买入 Protective Put 对冲下行风险
        </p>
      </div>

      {/* 策略切换 */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem' }}>
        {[
          { id: 'covered_call', label: '📈 Covered Call（增收）', color: '16,185,129' },
          { id: 'protective_put', label: '🛡️ Protective Put（对冲）', color: '239,68,68' },
        ].map(({ id, label, color }) => (
          <button
            key={id}
            onClick={() => { setMode(id); setResult(null); setError(null); }}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '8px',
              border: `1px solid rgba(${color},${mode === id ? '0.5' : '0.15'})`,
              background: mode === id ? `rgba(${color},0.15)` : 'transparent',
              color: mode === id ? `rgb(${color})` : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: mode === id ? 700 : 400,
              fontSize: '0.85rem',
              transition: 'all 0.2s',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 知识卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem', marginBottom: '1.5rem' }}>
        {mode === 'covered_call' ? (
          <>
            <KnowledgeCard
              title="📈 什么是 Covered Call？"
              color="16,185,129"
              items={[
                '你持有 100 股某股票，同时卖出 1 张该股票的看涨期权（Call）',
                '买方支付权利金给你，换取在行权价买走你股票的权利',
                '若股价未涨到行权价：权利金全归你，股票留着继续持有',
                '若股价超过行权价：股票被买走，但你获得行权价差 + 权利金',
                '最佳场景：股价横盘或温和上涨，每月稳定收取权利金',
              ]}
            />
            <KnowledgeCard
              title="💡 使用建议"
              color="59,130,246"
              items={[
                '选择 OTM 5-15% 的行权价，既保留上涨空间又有足够权利金',
                '优先选 30-45 天到期：Theta 衰减最快，性价比最高',
                'Delta < 0.30 = 被行权概率较低；Delta > 0.50 = 权利金高但风险大',
                '年化收益 10-25% 是合理目标；超过 30% 通常说明被行权概率偏高',
                '财报前 2 周不要卖出 Covered Call（IV 虚高，可能剧烈波动）',
              ]}
            />
          </>
        ) : (
          <>
            <KnowledgeCard
              title="🛡️ 什么是 Protective Put？"
              color="239,68,68"
              items={[
                '你持有股票，同时买入该股票的看跌期权（Put）作为"保险"',
                '若股价大跌：Put 期权价值上涨，对冲持股损失',
                '若股价上涨：Put 到期归零，损失权利金（保险费）',
                '最大亏损 = (现价 - 行权价) × 股数 + 权利金，不会更多',
                '适合在波动加剧前（如财报季、宏观事件前）保护持仓',
              ]}
            />
            <KnowledgeCard
              title="💡 使用建议"
              color="245,158,11"
              items={[
                '保护水位 -10% 是常见选择：权利金合理，保护有效',
                'OTM -5% 保护成本高，适合强烈看跌担忧时',
                'OTM -20% 保护成本低，仅防黑天鹅（大幅崩盘）',
                '年化成本 < 3% 是理想值；超过 5% 可考虑改用期权组合策略',
                '可用 Covered Call 的权利金收入来补贴 Put 的保险费（Collar 策略）',
              ]}
            />
          </>
        )}
      </div>

      {/* 输入表单 */}
      <div className="glass-panel" style={{ padding: '1.25rem', marginBottom: '1.25rem' }}>
        <form onSubmit={handleSearch}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ minWidth: '120px' }}>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>股票代码</label>
              <input
                type="text"
                value={symbol}
                onChange={e => setSymbol(e.target.value.toUpperCase())}
                placeholder="AAPL"
                required
                style={{ ...inputStyle, textTransform: 'uppercase' }}
              />
            </div>
            <div style={{ minWidth: '100px' }}>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>持有股数</label>
              <input
                type="number"
                value={shares}
                onChange={e => setShares(e.target.value)}
                placeholder="100"
                min="1"
                required
                style={inputStyle}
              />
            </div>
            <div style={{ minWidth: '130px' }}>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                {mode === 'covered_call' ? '持仓成本价（可选）' : '买入成本价（可选）'}
              </label>
              <input
                type="number"
                value={costBasis}
                onChange={e => setCostBasis(e.target.value)}
                placeholder={mode === 'covered_call' ? '如 180.00（影响收益率计算）' : '如 180.00'}
                min="0"
                step="0.01"
                style={inputStyle}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              style={{
                background: mode === 'covered_call' ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.15)',
                border: `1px solid rgba(${mode === 'covered_call' ? '16,185,129' : '239,68,68'},0.4)`,
                color: mode === 'covered_call' ? '#10b981' : '#ef4444',
                padding: '0.45rem 1.25rem',
                borderRadius: '8px',
                cursor: loading ? 'wait' : 'pointer',
                fontWeight: 600,
                fontSize: '0.85rem',
                whiteSpace: 'nowrap',
              }}
            >
              {loading ? '⟳ 查询中…' : mode === 'covered_call' ? '查找 Covered Call' : '查找 Protective Put'}
            </button>
          </div>
        </form>
      </div>

      {error && <ErrorBox message={error} />}

      {/* 结果 */}
      {result && (
        <div className="glass-panel" style={{ padding: '1.25rem' }}>
          <h3 style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '0' }}>
            {result.mode === 'covered_call'
              ? `📈 ${result.data.symbol} Covered Call 建议`
              : `🛡️ ${result.data.symbol} Protective Put 建议`}
          </h3>
          {result.mode === 'covered_call'
            ? <CoveredCallTable data={result.data} shares={parseInt(shares) || 100} />
            : <ProtectivePutTable data={result.data} shares={parseInt(shares) || 100} />}
        </div>
      )}

      {!result && !loading && !error && (
        <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <p style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>{mode === 'covered_call' ? '📈' : '🛡️'}</p>
          <p>输入股票代码和持有股数，查看{mode === 'covered_call' ? 'Covered Call 建议（卖出 Call 收取权利金）' : 'Protective Put 建议（买入 Put 对冲下行风险）'}</p>
        </div>
      )}
    </div>
  );
}
