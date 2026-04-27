import { useEffect, useState } from 'react';
import { X, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { API_BASE } from '../../hooks/useApi';
import Tooltip from '../../components/ui/Tooltip';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import PnLChart from '../../charts/PnLChart';
import PriceHistoryChart from '../../charts/PriceHistoryChart';
import { TIPS } from '../../constants/tooltips';

const STRATEGY_CONFIG = {
  sell_put:  { label: '卖出 Put', color: '#10b981' },
  buy_call:  { label: '买入 Call', color: '#8b5cf6' },
  sell_call: { label: '卖出 Call', color: '#f59e0b' },
  buy_put:   { label: '买入 Put', color: '#ef4444' },
};

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-primary)', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '0.5rem' }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

export default function DetailModal({ option, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [rollPlan, setRollPlan] = useState(null);
  const [loadingRoll, setLoadingRoll] = useState(false);

  useEffect(() => {
    if (!option) return;
    setLoading(true);
    setError(null);
    fetch(
      `${API_BASE}/api/analyze/${option.symbol}?strike=${option.strike}&dte=${option.dte}&current_price=${option.currentPrice}&strategy=${option.strategy}`
    )
      .then(r => { if (!r.ok) throw new Error('分析失败'); return r.json(); })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
      
    if (option.strategy === 'sell_put') {
      setLoadingRoll(true);
      fetch(`${API_BASE}/api/simulate-roll/${option.symbol}?strike=${option.strike}&dte=${option.dte}&premium=${option.premium}`)
        .then(r => r.json())
        .then(res => {
          if (res.status === 'success') setRollPlan(res.data);
        })
        .catch(e => console.error(e))
        .finally(() => setLoadingRoll(false));
    }
  }, [option]);

  if (!option) return null;

  const cfg = STRATEGY_CONFIG[option.strategy] || STRATEGY_CONFIG.sell_put;
  const isSell = option.strategy.startsWith('sell_');

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
        backdropFilter: 'blur(6px)', display: 'flex', justifyContent: 'center',
        alignItems: 'center', zIndex: 1000, padding: '1rem',
      }}
    >
      <div
        className="glass-panel"
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: '920px', maxHeight: '92vh',
          overflowY: 'auto', padding: '1.75rem', position: 'relative',
        }}
      >
        {/* 关闭按钮 */}
        <button
          onClick={onClose}
          style={{ position: 'absolute', top: '1rem', right: '1rem', background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
        >
          <X size={22} />
        </button>

        {/* 标题 */}
        <div style={{ marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 800 }}>{option.symbol}</h2>
            <span style={{ background: `${cfg.color}1a`, color: cfg.color, padding: '0.2rem 0.75rem', borderRadius: '999px', fontSize: '0.78rem', fontWeight: 700, border: `1px solid ${cfg.color}44` }}>
              {cfg.label}
            </span>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              行权价 ${option.strike} · 现价 ${option.currentPrice} · {option.dte} 天到期
            </span>
          </div>
        </div>

        {loading ? (
          <LoadingSpinner message="正在拉取历史数据和新闻分析，请稍候…" />
        ) : error ? (
          <div style={{ color: '#fca5a5', padding: '1rem', borderLeft: '4px solid #ef4444' }}>⚠️ {error}</div>
        ) : (
          <>
            {/* ── 损益图 ── */}
            <Section title="📊 到期损益图（每合约）">
              <PnLChart
                currentPrice={option.currentPrice}
                strike={option.strike}
                premium={option.premium}
                strategy={option.strategy}
              />
            </Section>

            {/* ── 历史验证 ── */}
            {data?.historicalStats && (
              <Section title="🛡️ 历史回测验证（过去 2 年）">
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
                  {[
                    { label: '总测试窗口', value: data.historicalStats.totalWindows, color: null },
                    { label: '安全窗口（股价未触及行权价）', value: data.historicalStats.safeWindows, color: '#10b981' },
                    { label: '触发窗口（曾跌破行权价）', value: data.historicalStats.triggeredWindows, color: data.historicalStats.triggeredWindows > 0 ? '#f59e0b' : null },
                  ].map(({ label, value, color }) => (
                    <div key={label} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '0.75rem', textAlign: 'center' }}>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>{label}</div>
                      <div style={{ fontSize: '1.4rem', fontWeight: 700, color: color || 'var(--text-primary)' }}>{value}</div>
                    </div>
                  ))}
                </div>

                <div style={{ padding: '0.75rem 1rem', background: 'rgba(16,185,129,0.08)', borderLeft: '3px solid #10b981', borderRadius: '0 8px 8px 0', marginBottom: '1rem' }}>
                  <Tooltip text={TIPS.popEmpirical}>
                    <span style={{ fontSize: '0.85rem', color: '#10b981', fontWeight: 700 }}>
                      历史胜率：{data.historicalStats.winRate}%
                    </span>
                  </Tooltip>
                </div>

                {data.historicalStats.triggeredEvents?.length > 0 && (
                  <details style={{ marginBottom: '0.5rem' }}>
                    <summary style={{ cursor: 'pointer', fontSize: '0.82rem', color: '#f59e0b', marginBottom: '0.5rem' }}>
                      ⚠️ 查看 {data.historicalStats.triggeredEvents.length} 次历史触发事件（市场崩跌记录）
                    </summary>
                    <Tooltip text={TIPS.wheelStrategy} width={300}>
                      <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: '1.6', marginBottom: '0.5rem' }}>
                        💼 即使被触发，并不代表一定亏损。通过向后滚仓（Roll Out）或接受转为持股（Wheel 策略），往往可以将暂时的亏损转化为时间损失而非真正的资本损失。
                      </p>
                    </Tooltip>
                    <div style={{ maxHeight: '200px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      {data.historicalStats.triggeredEvents.map((ev, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem', background: 'rgba(0,0,0,0.2)', borderRadius: '6px', fontSize: '0.8rem' }}>
                          <span style={{ color: 'var(--text-secondary)' }}>开始：{ev.date}</span>
                          <span>${ev.start_price} → <span style={{ color: '#ef4444' }}>${ev.min_price}</span></span>
                          <span style={{ color: '#ef4444', fontWeight: 700 }}>-{ev.drawdown_pct}%</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
                
                {/* ── Backup Plan Simulator ── */}
                {option.strategy === 'sell_put' && (
                  <div style={{ padding: '1rem', background: 'rgba(59,130,246,0.08)', borderLeft: '4px solid #3b82f6', borderRadius: '8px', marginTop: '1rem' }}>
                    <h4 style={{ color: '#60a5fa', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      🚑 备用计划: 假设今日击穿向下延期 (Roll Down & Out)
                    </h4>
                    {loadingRoll ? (
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>正在实时检索市场最新合约...</div>
                    ) : rollPlan ? (
                      <div>
                        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: '1.6', marginBottom: '0.75rem' }}>
                          假设股价在到期时跌破行权价 2% (${(option.strike * 0.98).toFixed(2)})，你花大约 <strong>${rollPlan.btc_cost.toFixed(2)}</strong> 买平被套期权（Buy To Close）。<br/>
                          立刻往后延期至 <strong>{rollPlan.roll_date}</strong> (延后 {rollPlan.roll_dte - option.dte} 天)，卖出更低行权价 <strong>${rollPlan.roll_strike.toFixed(2)}</strong> 的新期权，收入 <strong>${rollPlan.roll_premium.toFixed(2)}</strong>（Sell To Open）。
                        </p>
                        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                          <div style={{ padding: '0.5rem 1rem', background: 'rgba(16,185,129,0.1)', borderRadius: '6px', border: '1px solid rgba(16,185,129,0.3)' }}>
                            <div style={{ fontSize: '0.75rem', color: '#10b981' }}>额外净收入 (Net Credit)</div>
                            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#10b981' }}>+${rollPlan.net_credit.toFixed(2)}</div>
                          </div>
                          <div style={{ padding: '0.5rem 1rem', background: 'rgba(59,130,246,0.1)', borderRadius: '6px', border: '1px solid rgba(59,130,246,0.3)' }}>
                            <div style={{ fontSize: '0.75rem', color: '#60a5fa' }}>新安全垫降低</div>
                            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#60a5fa' }}>-${(option.strike - rollPlan.roll_strike).toFixed(2)}</div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>暂无合适的远期无风险净收入合约。此时建议直接接盘正股并卖出 Covered Call (Wheel Strategy)。</div>
                    )}
                  </div>
                )}
              </Section>
            )}

            {/* ── 历史价格图 ── */}
            {data?.chartData && (
              <Section title="📈 历史价格走势">
                <PriceHistoryChart
                  chartData={data.chartData}
                  strike={option.strike}
                  expectedUpper={option.expectedMoveUpper}
                  expectedLower={option.expectedMoveLower}
                />
              </Section>
            )}

            {/* ── 新闻情绪 ── */}
            {data?.newsAnalysis && (
              <Section title="📰 近期新闻情绪分析">
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem', padding: '0.75rem 1rem', background: 'rgba(255,255,255,0.04)', borderRadius: '8px' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>整体情绪：</span>
                  <span style={{
                    fontWeight: 700, fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '0.4rem',
                    color: data.newsAnalysis.overallSentiment === '看涨' ? '#10b981' : data.newsAnalysis.overallSentiment === '看跌' ? '#ef4444' : '#f59e0b',
                  }}>
                    {data.newsAnalysis.overallSentiment === '看涨' && <TrendingUp size={18} />}
                    {data.newsAnalysis.overallSentiment === '看跌' && <TrendingDown size={18} />}
                    {data.newsAnalysis.overallSentiment === '中性' && <Minus size={18} />}
                    {data.newsAnalysis.overallSentiment}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>（基于标题 VADER 情绪分析）</span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {data.newsAnalysis.articles.length === 0 ? (
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>暂无近期新闻</p>
                  ) : data.newsAnalysis.articles.map((art, i) => (
                    <div key={i} style={{ padding: '0.75rem', border: '1px solid var(--card-border)', borderRadius: '8px' }}>
                      <a href={art.link} target="_blank" rel="noreferrer" style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '0.85rem', textDecoration: 'none', display: 'block', marginBottom: '0.4rem' }}>
                        {art.title}
                      </a>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        <span>{art.publisher || '财经媒体'}</span>
                        <span style={{ color: art.sentimentScore > 0.15 ? '#10b981' : art.sentimentScore < -0.15 ? '#ef4444' : '#f59e0b' }}>
                          情绪：{art.sentimentScore > 0 ? '+' : ''}{art.sentimentScore.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
