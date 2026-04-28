import { useState, useEffect, useRef } from 'react';
import { RefreshCw, AlertTriangle, Calendar, CheckCircle } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import { ErrorBox } from '../../components/ui/LoadingSpinner';
import Tooltip from '../../components/ui/Tooltip';
import { TIPS } from '../../constants/tooltips';

const STEPS = [
  { label: '连接财报数据源（FMP）', duration: 1500 },
  { label: '获取未来 90 天财报日历', duration: 2000 },
  { label: '批量查询 20 只股票现价', duration: 2500 },
  { label: '计算预期波动幅度', duration: 2000 },
  { label: '整理并排序数据', duration: 1000 },
];

function EarningsProgress() {
  const [stepIndex, setStepIndex] = useState(0);
  const timerRef = useRef(null);

  useEffect(() => {
    const advance = (i) => {
      if (i >= STEPS.length - 1) return;
      timerRef.current = setTimeout(() => {
        setStepIndex(i + 1);
        advance(i + 1);
      }, STEPS[i].duration);
    };
    advance(0);
    return () => clearTimeout(timerRef.current);
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '40vh', gap: '1.5rem' }}>
      <div className="spinner" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', minWidth: '260px' }}>
        {STEPS.map((step, i) => {
          const done = i < stepIndex;
          const active = i === stepIndex;
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', opacity: i > stepIndex ? 0.3 : 1, transition: 'opacity 0.3s' }}>
              {done
                ? <CheckCircle size={15} color="#10b981" />
                : <div style={{ width: 15, height: 15, borderRadius: '50%', border: `2px solid ${active ? '#60a5fa' : 'rgba(255,255,255,0.2)'}`, flexShrink: 0, background: active ? 'rgba(96,165,250,0.15)' : 'transparent', transition: 'all 0.3s' }} />
              }
              <span style={{ fontSize: '0.82rem', color: done ? '#10b981' : active ? 'var(--text-primary)' : 'var(--text-secondary)', fontWeight: active ? 600 : 400, transition: 'color 0.3s' }}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function EarningsTab() {
  const { data, loading, error, refetch } = useApi('/api/earnings');
  const earnings = data?.data || [];

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Calendar size={22} color="var(--accent-color)" /> 财报雷达
          </h2>
          <div className="glass-panel" style={{ padding: '0.75rem 1rem', marginTop: '0.75rem', borderLeft: '4px solid #f59e0b' }}>
            <Tooltip text={TIPS.earnings} width={320}>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                ⚠️ <strong style={{ color: '#f59e0b' }}>财报前后，绝对不要卖短期期权！</strong>
                财报会导致 IV 暴涨随后急跌（IV Crush），股价也会大幅跳空，破坏所有统计优势。
                <span style={{ color: 'rgba(148,163,184,0.6)', fontSize: '0.78rem', display: 'block', marginTop: '4px' }}>点击 ⓘ 了解更多 →</span>
              </p>
            </Tooltip>
          </div>
        </div>
        <button
          onClick={() => refetch()}
          disabled={loading}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            color: 'var(--text-primary)', padding: '0.45rem 0.9rem',
            borderRadius: '8px', cursor: loading ? 'not-allowed' : 'pointer', fontSize: '0.82rem',
          }}
        >
          <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} /> 刷新
        </button>
      </div>

      {loading ? (
        <EarningsProgress />
      ) : error ? (
        <ErrorBox message={error} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '1rem' }}>
          {earnings.map((item) => {
            const isDanger = item.daysAway >= 0 && item.daysAway <= 14;
            const isPast = item.daysAway < 0;

            return (
              <div
                key={item.symbol}
                className="glass-panel"
                style={{
                  padding: '1.1rem',
                  borderLeft: `4px solid ${isDanger ? '#ef4444' : isPast ? 'rgba(255,255,255,0.1)' : '#10b981'}`,
                  opacity: isPast ? 0.5 : 1,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <span style={{ fontSize: '1.3rem', fontWeight: 700 }}>{item.symbol}</span>
                  {isDanger && <AlertTriangle size={18} color="#ef4444" />}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.82rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>财报日</span>
                    <span style={{ fontWeight: 600 }}>{item.earningsDate}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>距今</span>
                    <span style={{
                      fontWeight: 700,
                      color: isDanger ? '#ef4444' : isPast ? 'var(--text-secondary)' : '#10b981',
                    }}>
                      {isPast ? '已公布' : `${item.daysAway} 天后`}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>当前价</span>
                    <span>${item.currentPrice.toFixed(2)}</span>
                  </div>
                  {item.expectedMovePct != null && (
                    <div style={{ marginTop: '0.25rem', padding: '0.5rem', background: 'rgba(255,255,255,0.04)', borderRadius: '6px' }}>
                      <Tooltip text={TIPS.expectedMove} width={280}>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '3px' }}>预期波动幅度（±1σ）</div>
                      </Tooltip>
                      <div style={{ fontWeight: 700, color: '#60a5fa' }}>
                        ±${item.expectedMoveDollar} &nbsp;
                        <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>（±{item.expectedMovePct}%）</span>
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                        预计区间：${(item.currentPrice - item.expectedMoveDollar).toFixed(2)} ~ ${(item.currentPrice + item.expectedMoveDollar).toFixed(2)}
                      </div>
                    </div>
                  )}
                </div>

                {isDanger && (
                  <div style={{ marginTop: '0.75rem', padding: '0.5rem 0.75rem', background: 'rgba(239,68,68,0.1)', borderRadius: '6px', fontSize: '0.75rem', color: '#fca5a5' }}>
                    ⛔ 14 天内有财报，不建议卖出到期日跨过财报日的期权
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
