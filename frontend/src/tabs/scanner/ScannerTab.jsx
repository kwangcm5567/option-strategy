import { useState, useEffect } from 'react';
import { RefreshCw, Filter } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import { ErrorBox } from '../../components/ui/LoadingSpinner';
import Tooltip from '../../components/ui/Tooltip';
import OptionCard from './OptionCard';
import DetailModal from './DetailModal';
import { TIPS } from '../../constants/tooltips';

// ── 首次扫描专用 Loading（仅在没有任何数据时显示）────────────────────────────
const SCAN_STEPS = [
  '正在连接 Yahoo Finance 数据源…',
  '正在获取 AAPL / MSFT / NVDA 期权链…',
  '正在获取 AMZN / TSLA / GOOGL 期权链…',
  '正在获取 META / JPM / V 期权链…',
  '正在获取 JNJ / UNH / XOM 期权链…',
  '正在获取 CVX / PG / KO 期权链…',
  '正在获取 HD / COST / ABBV 期权链…',
  '正在获取 CRM / NFLX 期权链…',
  '正在运行历史回测（2 年滚动窗口）…',
  '正在用 Black-Scholes 计算 Greeks…',
  '正在计算 IV Rank / 预期波动区间…',
  '正在过滤和排序结果，快好了…',
];

function ScannerLoading() {
  const [elapsed, setElapsed] = useState(0);
  const [step, setStep] = useState(0);

  useEffect(() => {
    const t1 = setInterval(() => setElapsed(s => s + 1), 1000);
    const t2 = setInterval(() => setStep(s => (s + 1) % SCAN_STEPS.length), 6000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, []);

  const pct = Math.min(Math.round((elapsed / 150) * 100), 95);
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const timeStr = mins > 0 ? `${mins} 分 ${secs} 秒` : `${secs} 秒`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '55vh', gap: '1.5rem' }}>
      <div style={{ width: 64, height: 64 }}>
        <div className="spinner" style={{ width: 64, height: 64, borderWidth: 5 }} />
      </div>
      <div style={{ textAlign: 'center' }}>
        <p style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.3rem' }}>
          正在扫描全市场期权…
        </p>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
          首次扫描约需 <strong style={{ color: '#f59e0b' }}>60–120 秒</strong>，之后 1 小时内直接读缓存（秒开）
        </p>
      </div>
      <div style={{ width: '100%', maxWidth: 420 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '6px' }}>
          <span>扫描进度</span>
          <span style={{ color: '#60a5fa', fontWeight: 600 }}>{pct}%</span>
        </div>
        <div style={{ height: 8, background: 'rgba(255,255,255,0.08)', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: 'linear-gradient(to right, #3b82f6, #8b5cf6)', borderRadius: 4, transition: 'width 1s ease' }} />
        </div>
      </div>
      <div style={{ padding: '0.6rem 1.2rem', background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(96,165,250,0.2)', borderRadius: 8, fontSize: '0.82rem', color: '#93c5fd', maxWidth: 420, textAlign: 'center', minHeight: 36 }}>
        {SCAN_STEPS[step]}
      </div>
      <p style={{ fontSize: '0.78rem', color: 'rgba(148,163,184,0.5)' }}>
        已等待 {timeStr} · 请耐心等候，窗口正在工作中
      </p>
    </div>
  );
}

// ── 刷新中横幅（有数据时显示，不遮盖卡片）────────────────────────────────────
function RefreshingBanner() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '0.75rem',
      padding: '0.6rem 1rem', marginBottom: '1rem',
      background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(96,165,250,0.2)',
      borderRadius: 8, fontSize: '0.82rem', color: '#93c5fd',
    }}>
      <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2, flexShrink: 0 }} />
      正在后台重新扫描，完成后自动更新，请稍候…
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

const STRATEGY_OPTIONS = [
  { value: 'sell_put',  label: '卖出 Put',  tip: TIPS.strategies.sell_put  },
  { value: 'buy_call',  label: '买入 Call', tip: TIPS.strategies.buy_call  },
  { value: 'sell_call', label: '卖出 Call', tip: TIPS.strategies.sell_call },
  { value: 'buy_put',   label: '买入 Put',  tip: TIPS.strategies.buy_put   },
];

function buildEndpoint(strategies, dteMin, dteMax, ivRank) {
  const s = strategies.join(',') || 'sell_put';
  return `/api/scan?strategies=${encodeURIComponent(s)}&dte_min=${dteMin}&dte_max=${dteMax}&min_iv_rank=${ivRank}`;
}

export default function ScannerTab() {
  const [selectedStrategies, setSelectedStrategies] = useState(['sell_put']);
  const [dteMin, setDteMin] = useState(7);
  const [dteMax, setDteMax] = useState(60);
  const [minIvRank, setMinIvRank] = useState(0);
  const [hideEarningsRisk, setHideEarningsRisk] = useState(false);
  const [showStandards, setShowStandards] = useState(false);
  const [selectedOption, setSelectedOption] = useState(null);
  const [lastGoodOptions, setLastGoodOptions] = useState([]);

  const endpoint = buildEndpoint(selectedStrategies, dteMin, dteMax, minIvRank);
  const { data, loading, error, refetch } = useApi(endpoint, { timeout: 180_000 });

  useEffect(() => {
    if (data?.data?.length > 0) {
      setLastGoodOptions(data.data);
    }
  }, [data]);

  const toggleStrategy = (val) => {
    setSelectedStrategies(prev =>
      prev.includes(val) ? prev.filter(s => s !== val) : [...prev, val]
    );
  };

  const handleRefresh = () => {
    refetch(endpoint + '&force_refresh=true');
  };

  const isInitialLoad = loading && lastGoodOptions.length === 0;
  const isRefreshing  = loading && lastGoodOptions.length > 0;
  const rawOptions = data?.data || lastGoodOptions;
  const displayOptions = hideEarningsRisk
    ? rawOptions.filter(o => !o.earningsRisk)
    : rawOptions;
  const hiddenEarningsCount = hideEarningsRisk
    ? rawOptions.filter(o => o.earningsRisk).length
    : 0;

  return (
    <div style={{ animation: 'fadeInUp 0.4s ease-out' }}>

      {/* ── 筛选控制栏 ── */}
      <div className="glass-panel" style={{ padding: '1rem 1.25rem', marginBottom: '1.5rem', display: 'flex', flexWrap: 'wrap', gap: '1.25rem', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          <Filter size={15} /> 筛选
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {STRATEGY_OPTIONS.map(({ value, label, tip }) => (
            <Tooltip key={value} text={tip} width={280}>
              <button
                onClick={() => toggleStrategy(value)}
                style={{
                  padding: '0.35rem 0.9rem', borderRadius: '999px', cursor: 'pointer', fontSize: '0.8rem',
                  fontWeight: selectedStrategies.includes(value) ? 700 : 400,
                  border: `1px solid ${selectedStrategies.includes(value) ? 'rgba(96,165,250,0.6)' : 'rgba(255,255,255,0.1)'}`,
                  background: selectedStrategies.includes(value) ? 'rgba(59,130,246,0.2)' : 'transparent',
                  color: selectedStrategies.includes(value) ? '#60a5fa' : 'var(--text-secondary)',
                  transition: 'all 0.2s',
                }}
              >
                {label}
              </button>
            </Tooltip>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
          <span>到期天数</span>
          <input type="number" min={1} max={dteMax - 1} value={dteMin}
            onChange={e => setDteMin(+e.target.value)}
            style={{ width: '48px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'var(--text-primary)', padding: '0.2rem 0.4rem', textAlign: 'center', fontSize: '0.82rem' }}
          />
          <span>–</span>
          <input type="number" min={dteMin + 1} max={365} value={dteMax}
            onChange={e => setDteMax(+e.target.value)}
            style={{ width: '48px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'var(--text-primary)', padding: '0.2rem 0.4rem', textAlign: 'center', fontSize: '0.82rem' }}
          />
          <span>天</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
          <Tooltip text={TIPS.ivRank}><span>最低 IV Rank</span></Tooltip>
          <input type="number" min={0} max={100} value={minIvRank}
            onChange={e => setMinIvRank(+e.target.value)}
            style={{ width: '52px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'var(--text-primary)', padding: '0.2rem 0.4rem', textAlign: 'center', fontSize: '0.82rem' }}
          />
          <span>%</span>
        </div>

        {/* ── 财报高危开关 ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <button
            onClick={() => setHideEarningsRisk(v => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.4rem',
              padding: '0.35rem 0.75rem', borderRadius: '8px', cursor: 'pointer',
              fontSize: '0.78rem', transition: 'all 0.2s',
              border: hideEarningsRisk
                ? '1px solid rgba(239,68,68,0.5)'
                : '1px solid rgba(255,255,255,0.15)',
              background: hideEarningsRisk
                ? 'rgba(239,68,68,0.12)'
                : 'rgba(16,185,129,0.08)',
              color: hideEarningsRisk ? '#fca5a5' : '#6ee7b7',
            }}
          >
            {hideEarningsRisk ? '⛔ 隐藏财报高危期权（已开启）' : '✅ 显示所有期权（含财报高危）'}
          </button>
          <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', paddingLeft: '4px' }}>
            点击切换：财报前期权风险较高
          </span>
        </div>

        <button
          onClick={handleRefresh}
          disabled={loading}
          style={{
            marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.4rem',
            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            color: 'var(--text-primary)', padding: '0.4rem 1rem', borderRadius: '8px',
            cursor: loading ? 'not-allowed' : 'pointer', fontSize: '0.82rem', transition: 'all 0.2s',
          }}
        >
          <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          {loading ? '扫描中…' : '刷新数据'}
        </button>
      </div>

      {/* ── 机构筛选标准说明（可折叠）── */}
      <div className="glass-panel" style={{ padding: '0.7rem 1.25rem', marginBottom: '1rem' }}>
        <button
          onClick={() => setShowStandards(v => !v)}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'none', border: 'none', color: 'var(--text-primary)', cursor: 'pointer', width: '100%', padding: 0, textAlign: 'left' }}
        >
          <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>📐 机构筛选标准</span>
          <span style={{ fontSize: '0.7rem', color: '#60a5fa', background: 'rgba(59,130,246,0.12)', padding: '0.1rem 0.5rem', borderRadius: '999px', border: '1px solid rgba(96,165,250,0.25)' }}>已激活</span>
          <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{showStandards ? '▲ 收起' : '▼ 展开'}</span>
        </button>
        {showStandards && (() => {
          const hasSell = selectedStrategies.some(s => s.startsWith('sell_'));
          const hasBuy  = selectedStrategies.includes('buy_call') || selectedStrategies.includes('buy_put');
          const sellStds = [
            { label: 'σ-距离 ≥ 1.0σ', desc: '行权价须超出预期波动幅度，甜点在 1.2σ（约 Delta 0.20）', color: '#10b981' },
            { label: '|Δ| 0.10 – 0.40', desc: 'Delta 甜点区间，兼顾安全边际与权利金回报', color: '#60a5fa' },
            { label: '历史胜率 ≥ 70%', desc: '1年回测安全窗口 ≥ 70%，机构级确定性门槛', color: '#f59e0b' },
            { label: 'ROC ≤ 40%', desc: '年化资本回报率上限，过高意味着隐含风险过大', color: '#a78bfa' },
            { label: '年化回报 8–80%', desc: '筛除无意义低回报与极端高风险期权', color: '#fb7185' },
          ];
          const buyStds = [
            { label: 'IV Rank ≤ 25%', desc: '期权便宜时买入，不为 IV 溢价买单（买方核心时机）', color: '#8b5cf6' },
            { label: 'RSI 45–65', desc: '动量健康区间，避免超买（>70）追涨；<35 等反转确认', color: '#60a5fa' },
            { label: 'MACD 正向扩张', desc: '趋势向上确认，避免在动能衰竭时买入', color: '#10b981' },
            { label: '高于 SMA50 + SMA200', desc: '双均线确认多头格局，降低逆势建仓风险', color: '#f59e0b' },
            { label: 'Delta 0.35–0.55', desc: '足够方向性敞口，不过度依赖极端波动才获利', color: '#fb7185' },
          ];
          const StdGrid = ({ items, title, titleColor }) => (
            <div>
              {title && <div style={{ fontSize: '0.72rem', fontWeight: 700, color: titleColor, marginBottom: '0.4rem', marginTop: '0.5rem' }}>{title}</div>}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(185px, 1fr))', gap: '0.6rem' }}>
                {items.map(item => (
                  <div key={item.label} style={{ padding: '0.5rem 0.65rem', background: 'rgba(255,255,255,0.03)', borderRadius: '7px', borderLeft: `3px solid ${item.color}55` }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 700, color: item.color, marginBottom: '0.2rem' }}>{item.label}</div>
                    <div style={{ fontSize: '0.71rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>{item.desc}</div>
                  </div>
                ))}
              </div>
            </div>
          );
          return (
            <div style={{ marginTop: '0.75rem' }}>
              {hasSell && <StdGrid items={sellStds} title={hasBuy ? '📐 卖出策略标准（Sell Put / Sell Call）' : null} titleColor="#10b981" />}
              {hasBuy  && <StdGrid items={buyStds}  title={hasSell ? '📈 买入策略标准（Buy Call）' : null}            titleColor="#8b5cf6" />}
            </div>
          );
        })()}
      </div>

      {/* ── 内容区 ── */}

      {/* 首次加载：全屏 loading 动画 */}
      {isInitialLoad && <ScannerLoading />}

      {/* 刷新中：小横幅，卡片保持可见 */}
      {isRefreshing && <RefreshingBanner />}

      {/* 错误提示（非首次也显示） */}
      {!loading && error && <ErrorBox message={error} />}

      {/* 缓存提示 */}
      {!loading && !error && data?.cached && (
        <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          📦 数据来自缓存（1 小时内有效）· 点击「刷新数据」重新扫描
        </p>
      )}

      {/* 卡片列表（始终保留，刷新时不消失） */}
      {!isInitialLoad && (
        displayOptions.length === 0 && !loading && !error ? (
          <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center' }}>
            <h3>暂无符合条件的期权</h3>
            {hideEarningsRisk && hiddenEarningsCount > 0 ? (
              <div style={{ marginTop: '0.75rem' }}>
                <p style={{ color: '#fca5a5', fontSize: '0.9rem' }}>
                  ⛔ 所有 {hiddenEarningsCount} 个期权因财报风险被隐藏（当前处于财报季）
                </p>
                <button
                  onClick={() => setHideEarningsRisk(false)}
                  style={{ marginTop: '0.75rem', padding: '0.45rem 1.2rem', borderRadius: '8px', border: '1px solid rgba(96,165,250,0.4)', background: 'rgba(59,130,246,0.15)', color: '#60a5fa', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}
                >
                  显示全部（含财报高危）
                </button>
              </div>
            ) : (
              <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem', fontSize: '0.9rem' }}>
                当前市场条件不满足筛选标准，尝试放宽条件或点击刷新。
              </p>
            )}
          </div>
        ) : (
          <>
            {displayOptions.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: 0 }}>
                  找到 {displayOptions.length} 个符合条件的期权，按综合评分排列
                </p>
                {hiddenEarningsCount > 0 && (
                  <span style={{ fontSize: '0.75rem', color: '#fca5a5', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)', padding: '0.15rem 0.5rem', borderRadius: '999px' }}>
                    ⛔ 已隐藏 {hiddenEarningsCount} 条财报高危期权
                  </span>
                )}
              </div>
            )}
            <div className="dashboard-grid">
              {displayOptions.map((opt, i) => (
                <OptionCard
                  key={`${opt.symbol}-${opt.strategy}-${i}`}
                  option={opt}
                  onClick={() => setSelectedOption(opt)}
                />
              ))}
            </div>
          </>
        )
      )}

      {selectedOption && (
        <DetailModal option={selectedOption} onClose={() => setSelectedOption(null)} />
      )}
    </div>
  );
}
