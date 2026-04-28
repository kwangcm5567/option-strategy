import { useState } from 'react';
import { Search, ChevronDown, ChevronUp } from 'lucide-react';
import { API_BASE } from '../../hooks/useApi';
import Tooltip from '../../components/ui/Tooltip';
import LoadingSpinner, { ErrorBox } from '../../components/ui/LoadingSpinner';
import PnLChart from '../../charts/PnLChart';
import { TIPS } from '../../constants/tooltips';

const STRATEGIES = [
  { value: 'sell_put',  label: '卖出 Put',  tip: TIPS.strategies.sell_put  },
  { value: 'buy_call',  label: '买入 Call', tip: TIPS.strategies.buy_call  },
  { value: 'sell_call', label: '卖出 Call', tip: TIPS.strategies.sell_call },
  { value: 'buy_put',   label: '买入 Put',  tip: TIPS.strategies.buy_put   },
];

function GreeksRow({ label, value, tip, color }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.4rem 0', borderBottom: '1px solid rgba(255,255,255,0.05)', fontSize: '0.82rem' }}>
      <span style={{ color: 'var(--text-secondary)' }}>
        {tip ? <Tooltip text={tip}><span>{label}</span></Tooltip> : label}
      </span>
      <span style={{ fontWeight: 600, color: color || 'var(--text-primary)' }}>{value ?? 'N/A'}</span>
    </div>
  );
}

export default function StrategyTab() {
  const [symbol, setSymbol] = useState('');
  const [strategy, setStrategy] = useState('sell_put');
  const [chainData, setChainData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [selectedDateIdx, setSelectedDateIdx] = useState(0);
  const [showITM, setShowITM] = useState(false);

  const handleSearch = async () => {
    if (!symbol.trim()) return;
    setLoading(true);
    setError(null);
    setChainData(null);
    setSelected(null);
    setSelectedDateIdx(0);
    setShowITM(false);
    try {
      const res = await fetch(`${API_BASE}/api/option-chain/${symbol.trim().toUpperCase()}?strategy=${strategy}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || '获取期权链失败');
      }
      setChainData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const isSell = strategy.startsWith('sell_');
  const isCall = strategy.includes('call');
  const colCount = isSell ? 12 : 11;

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.25rem' }}>策略构建器</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem' }}>
          输入股票代码，选择策略，查看完整期权链和每个行权价的详细数据。
        </p>
      </div>

      {/* ── 搜索栏 ── */}
      <div className="glass-panel" style={{ padding: '1rem 1.25rem', marginBottom: '1.5rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
        <input
          value={symbol}
          onChange={e => setSymbol(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          placeholder="股票代码（如 AAPL）"
          style={{
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: '8px', color: 'var(--text-primary)', padding: '0.5rem 0.9rem',
            fontSize: '0.9rem', width: '160px', outline: 'none',
          }}
        />
        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
          {STRATEGIES.map(({ value, label, tip }) => (
            <Tooltip key={value} text={tip} width={280}>
              <button
                onClick={() => setStrategy(value)}
                style={{
                  padding: '0.35rem 0.85rem', borderRadius: '999px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: strategy === value ? 700 : 400,
                  border: `1px solid ${strategy === value ? 'rgba(96,165,250,0.6)' : 'rgba(255,255,255,0.1)'}`,
                  background: strategy === value ? 'rgba(59,130,246,0.2)' : 'transparent',
                  color: strategy === value ? '#60a5fa' : 'var(--text-secondary)', transition: 'all 0.2s',
                }}
              >
                {label}
              </button>
            </Tooltip>
          ))}
        </div>
        <button
          onClick={handleSearch}
          disabled={loading || !symbol.trim()}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            background: 'rgba(59,130,246,0.2)', border: '1px solid rgba(96,165,250,0.4)',
            color: '#60a5fa', padding: '0.5rem 1.1rem', borderRadius: '8px',
            cursor: loading || !symbol.trim() ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: 600,
          }}
        >
          <Search size={15} /> {loading ? '查询中…' : '查询'}
        </button>
      </div>

      {loading && <LoadingSpinner message={`正在获取 ${symbol} 的期权链，请稍候…`} />}
      {error && <ErrorBox message={error} />}

      {chainData && (
        <>
          {/* 股票概况 */}
          <div className="glass-panel" style={{ padding: '1rem 1.25rem', marginBottom: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center' }}>
            <div>
              <span style={{ fontSize: '1.6rem', fontWeight: 800 }}>{chainData.symbol}</span>
              <span style={{ color: 'var(--text-secondary)', marginLeft: '0.6rem', fontSize: '0.9rem' }}>
                现价：${chainData.currentPrice.toFixed(2)}
              </span>
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              <Tooltip text={TIPS.histVolatility}>历史波动率（HV）</Tooltip>：{chainData.histVolatility}%
            </div>
            <div style={{ fontSize: '0.82rem', color: chainData.aboveSma50 ? '#10b981' : '#ef4444' }}>
              50 日均线：${chainData.sma50?.toFixed(2)} · {chainData.aboveSma50 ? '▲ 在均线上方' : '▼ 在均线下方'}
            </div>
          </div>

          {/* 到期日 Tabs */}
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
            {chainData.chain.map(({ expirationDate, dte }, idx) => (
              <button
                key={expirationDate}
                onClick={() => { setSelectedDateIdx(idx); setSelected(null); }}
                style={{
                  padding: '0.35rem 0.75rem', borderRadius: '8px', cursor: 'pointer', fontSize: '0.8rem',
                  fontWeight: selectedDateIdx === idx ? 700 : 400,
                  border: `1px solid ${selectedDateIdx === idx ? 'rgba(96,165,250,0.6)' : 'rgba(255,255,255,0.1)'}`,
                  background: selectedDateIdx === idx ? 'rgba(59,130,246,0.2)' : 'transparent',
                  color: selectedDateIdx === idx ? '#60a5fa' : 'var(--text-secondary)', transition: 'all 0.2s',
                }}
              >
                {expirationDate}
                <span style={{ opacity: 0.6, marginLeft: '0.3rem', fontSize: '0.72rem' }}>{dte}天</span>
              </button>
            ))}
          </div>

          {/* 当前 Tab 的期权表 */}
          {chainData.chain[selectedDateIdx] && (() => {
            const { expirationDate, dte, options } = chainData.chain[selectedDateIdx];

            let displayOptions = [...options];

            // buy_call：只显示合理区间
            if (!isSell && isCall) {
              displayOptions = displayOptions.filter(opt =>
                opt.strike >= chainData.currentPrice * 0.92 &&
                opt.strike <= chainData.currentPrice * 1.20
              );
            }

            // sell 策略默认隐藏实值期权
            if (isSell && !showITM) {
              displayOptions = displayOptions.filter(opt => !opt.inTheMoney);
            }

            // put 从高到低排（ATM 在上），call 从低到高排（ATM 在上）
            displayOptions.sort((a, b) =>
              isCall ? a.strike - b.strike : b.strike - a.strike
            );

            // 在当前价格处插入分割线
            const rows = [];
            let dividerAdded = false;
            for (const opt of displayOptions) {
              if (!dividerAdded) {
                const crossed = isCall
                  ? opt.strike > chainData.currentPrice
                  : opt.strike < chainData.currentPrice;
                if (crossed) {
                  rows.push({ isDivider: true });
                  dividerAdded = true;
                }
              }
              rows.push(opt);
            }
            if (!dividerAdded) rows.push({ isDivider: true });

            const headers = isSell
              ? ['行权价', '权利金', '年化%', '买/卖价', '距离%', '平衡点', 'Delta ⓘ', 'Theta/天 ⓘ', 'IV%', 'IV Rank ⓘ', '理论 PoP ⓘ', '成交量']
              : ['行权价', '权利金', '买/卖价', '距离%', '平衡点', 'Delta ⓘ', 'Theta/天 ⓘ', 'IV%', 'IV Rank ⓘ', '理论 PoP ⓘ', '成交量'];

            return (
              <div style={{ marginBottom: '1.5rem' }}>
                {/* 表格工具栏 */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    到期日 <strong style={{ color: 'var(--text-primary)' }}>{expirationDate}</strong>（{dte} 天后）·
                    现价 <strong style={{ color: '#60a5fa' }}>${chainData.currentPrice.toFixed(2)}</strong>
                  </span>
                  {isSell && (
                    <button
                      onClick={() => setShowITM(v => !v)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: '0.3rem',
                        fontSize: '0.75rem', padding: '0.25rem 0.65rem', borderRadius: '6px', cursor: 'pointer',
                        border: '1px solid rgba(255,255,255,0.15)', background: showITM ? 'rgba(245,158,11,0.15)' : 'transparent',
                        color: showITM ? '#f59e0b' : 'var(--text-secondary)', transition: 'all 0.2s',
                      }}
                    >
                      {showITM ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                      {showITM ? '隐藏实值期权' : '展开实值期权'}
                    </button>
                  )}
                </div>

                <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-secondary)' }}>
                        {headers.map((h, i) => (
                          <th key={i} style={{ padding: '0.4rem 0.6rem', textAlign: 'right', fontWeight: 500, whiteSpace: 'nowrap', position: 'sticky', top: 0, background: '#0f172a', zIndex: 1 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((opt, i) => {
                        if (opt.isDivider) {
                          return (
                            <tr key="divider">
                              <td colSpan={colCount} style={{ padding: '0.3rem 0.6rem', textAlign: 'center', fontSize: '0.75rem', color: '#60a5fa', background: 'rgba(59,130,246,0.08)', fontWeight: 700, borderTop: '1px solid rgba(96,165,250,0.4)', borderBottom: '1px solid rgba(96,165,250,0.4)' }}>
                                ── 当前价 ${chainData.currentPrice.toFixed(2)} ──
                              </td>
                            </tr>
                          );
                        }

                        const annualReturn = isSell && dte > 0
                          ? ((opt.premium / (isCall ? chainData.currentPrice : opt.strike)) * (365 / dte) * 100).toFixed(1)
                          : null;

                        const cells = isSell
                          ? [
                              { val: `$${opt.strike.toFixed(2)}`, color: opt.inTheMoney ? '#f59e0b' : 'var(--text-primary)' },
                              { val: `$${opt.premium.toFixed(2)}`, color: '#60a5fa' },
                              { val: annualReturn ? `${annualReturn}%` : '—', color: parseFloat(annualReturn) >= 15 ? '#10b981' : parseFloat(annualReturn) >= 8 ? '#f59e0b' : 'var(--text-secondary)' },
                              { val: `$${opt.bid}/$${opt.ask}`, color: 'var(--text-secondary)' },
                              { val: `${opt.distancePct?.toFixed(1)}%`, color: (opt.distancePct || 0) >= 5 ? '#10b981' : '#f59e0b' },
                              { val: `$${opt.breakEven?.toFixed(2)}` },
                              { val: opt.delta?.toFixed(3) ?? 'N/A' },
                              { val: opt.thetaPerDay != null ? `+$${Math.abs(opt.thetaPerDay).toFixed(2)}` : 'N/A', color: '#10b981' },
                              { val: `${opt.impliedVolatility}%` },
                              { val: `${opt.ivRank}%`, color: opt.ivRank >= 60 ? '#ef4444' : opt.ivRank >= 30 ? '#f59e0b' : '#10b981' },
                              { val: opt.popTheoretical != null ? `${opt.popTheoretical}%` : 'N/A', color: (opt.popTheoretical || 0) >= 70 ? '#10b981' : '#f59e0b' },
                              { val: opt.volume.toLocaleString(), color: 'var(--text-secondary)' },
                            ]
                          : [
                              { val: `$${opt.strike.toFixed(2)}`, color: opt.inTheMoney ? '#f59e0b' : 'var(--text-primary)' },
                              { val: `$${opt.premium.toFixed(2)}`, color: '#60a5fa' },
                              { val: `$${opt.bid}/$${opt.ask}`, color: 'var(--text-secondary)' },
                              { val: `${opt.distancePct?.toFixed(1)}%`, color: (opt.distancePct || 0) >= 5 ? '#10b981' : '#f59e0b' },
                              { val: `$${opt.breakEven?.toFixed(2)}` },
                              { val: opt.delta?.toFixed(3) ?? 'N/A' },
                              { val: opt.thetaPerDay != null ? `-$${Math.abs(opt.thetaPerDay).toFixed(2)}` : 'N/A', color: '#ef4444' },
                              { val: `${opt.impliedVolatility}%` },
                              { val: `${opt.ivRank}%`, color: opt.ivRank >= 60 ? '#ef4444' : opt.ivRank >= 30 ? '#f59e0b' : '#10b981' },
                              { val: opt.popTheoretical != null ? `${opt.popTheoretical}%` : 'N/A', color: (opt.popTheoretical || 0) >= 70 ? '#10b981' : '#f59e0b' },
                              { val: opt.volume.toLocaleString(), color: 'var(--text-secondary)' },
                            ];

                        return (
                          <tr
                            key={i}
                            onClick={() => setSelected({ ...opt, expirationDate, dte, strategy, currentPrice: chainData.currentPrice, symbol: chainData.symbol })}
                            style={{
                              borderBottom: '1px solid rgba(255,255,255,0.04)',
                              cursor: 'pointer',
                              background: selected?.strike === opt.strike && selected?.expirationDate === expirationDate ? 'rgba(59,130,246,0.12)' : 'transparent',
                              transition: 'background 0.15s',
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.04)'}
                            onMouseLeave={e => e.currentTarget.style.background = selected?.strike === opt.strike ? 'rgba(59,130,246,0.12)' : 'transparent'}
                          >
                            {cells.map(({ val, color }, ci) => (
                              <td key={ci} style={{ padding: '0.45rem 0.6rem', textAlign: 'right', color: color || 'var(--text-primary)', whiteSpace: 'nowrap' }}>{val}</td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })()}

          {/* 选中行权价的详情面板 */}
          {selected && (
            <div className="glass-panel" style={{ padding: '1.25rem', marginTop: '1rem' }}>
              <h3 style={{ marginBottom: '1rem', fontWeight: 700 }}>
                {chainData.symbol} · {STRATEGIES.find(s => s.value === strategy)?.label} · 行权价 ${selected.strike}
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                <div>
                  <h4 style={{ fontSize: '0.85rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-secondary)' }}>Greeks & 波动率</h4>
                  <GreeksRow label="Delta" value={selected.delta?.toFixed(3)} tip={TIPS.delta} />
                  <GreeksRow label="Gamma" value={selected.gamma?.toFixed(5)} tip={TIPS.gamma} />
                  <GreeksRow label="Theta（每合约/天）" value={selected.thetaPerDay != null ? (isSell ? `+$${Math.abs(selected.thetaPerDay).toFixed(2)}` : `-$${Math.abs(selected.thetaPerDay).toFixed(2)}`) : 'N/A'} tip={TIPS.theta} color={isSell ? '#10b981' : '#ef4444'} />
                  <GreeksRow label="Vega（每合约/1% IV）" value={selected.vegaPerPct != null ? `$${selected.vegaPerPct.toFixed(2)}` : 'N/A'} tip={TIPS.vega} />
                  <GreeksRow label="隐含波动率（IV）" value={`${selected.impliedVolatility}%`} tip={TIPS.impliedVolatility} />
                  <GreeksRow label="IV Rank" value={`${selected.ivRank}%`} tip={TIPS.ivRank} color={selected.ivRank >= 60 ? '#ef4444' : '#f59e0b'} />
                </div>
                <div>
                  <h4 style={{ fontSize: '0.85rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-secondary)' }}>价格与概率</h4>
                  {isSell && selected.dte > 0 && (
                    <GreeksRow
                      label="年化回报率"
                      value={`${((selected.premium / (isCall ? selected.currentPrice : selected.strike)) * (365 / selected.dte) * 100).toFixed(1)}%`}
                      color="#10b981"
                    />
                  )}
                  <GreeksRow label="距离行权价" value={`${selected.distancePct?.toFixed(1)}%`} tip={TIPS.distancePct} color={(selected.distancePct || 0) >= 5 ? '#10b981' : '#f59e0b'} />
                  <GreeksRow label="盈亏平衡点" value={`$${selected.breakEven?.toFixed(2)}`} tip={TIPS.breakEven} />
                  <GreeksRow label="预期波动范围" value={`$${selected.expectedMoveLower} ~ $${selected.expectedMoveUpper} (±${selected.expectedMovePct}%)`} tip={TIPS.expectedMove} />
                  <GreeksRow label="理论获利概率" value={selected.popTheoretical != null ? `${selected.popTheoretical}%` : 'N/A'} tip={TIPS.popTheoretical} color={(selected.popTheoretical || 0) >= 70 ? '#10b981' : '#f59e0b'} />
                </div>
              </div>
              <div style={{ marginTop: '1.25rem' }}>
                <h4 style={{ fontSize: '0.85rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-secondary)' }}>到期损益图</h4>
                <PnLChart
                  currentPrice={chainData.currentPrice}
                  strike={selected.strike}
                  premium={selected.premium}
                  strategy={strategy}
                />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
