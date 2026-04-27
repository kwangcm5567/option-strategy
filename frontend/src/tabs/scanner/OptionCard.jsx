import Tooltip from '../../components/ui/Tooltip';
import { TIPS } from '../../constants/tooltips';

const STRATEGY_CONFIG = {
  sell_put:  { label: '卖出 Put', color: '#10b981', bg: 'rgba(16,185,129,0.1)'  },
  buy_call:  { label: '买入 Call', color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)' },
  sell_call: { label: '卖出 Call', color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  buy_put:   { label: '买入 Put', color: '#ef4444', bg: 'rgba(239,68,68,0.1)'   },
};

function IVRankBar({ value }) {
  const color = value >= 60 ? '#ef4444' : value >= 30 ? '#f59e0b' : '#10b981';
  const label = value >= 60 ? '期权偏贵，卖方有利' : value >= 30 ? '期权正常' : '期权便宜，买方有利';
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '3px', color: 'var(--text-secondary)' }}>
        <span>IV Rank</span>
        <span style={{ color }}>{value}% · {label}</span>
      </div>
      <div style={{ height: '5px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${value}%`, background: color, borderRadius: '3px', transition: 'width 0.8s ease' }} />
      </div>
    </div>
  );
}

function PoPBar({ theoretical, empirical }) {
  const agreement = theoretical != null && empirical != null && Math.abs(theoretical - empirical) <= 10;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {theoretical != null && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem', marginBottom: '3px', color: 'var(--text-secondary)' }}>
            <Tooltip text={TIPS.popTheoretical}><span>理论获利概率</span></Tooltip>
            <span style={{ color: theoretical >= 70 ? '#10b981' : '#f59e0b' }}>{theoretical}%</span>
          </div>
          <div style={{ height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${theoretical}%`, background: theoretical >= 70 ? '#10b981' : '#f59e0b', borderRadius: '2px' }} />
          </div>
        </div>
      )}
      {empirical != null && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem', marginBottom: '3px', color: 'var(--text-secondary)' }}>
            <Tooltip text={TIPS.popEmpirical}><span>历史回测胜率</span></Tooltip>
            <span style={{ color: empirical >= 70 ? '#10b981' : '#f59e0b' }}>{empirical}%</span>
          </div>
          <div style={{ height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${empirical}%`, background: empirical >= 70 ? '#10b981' : '#f59e0b', borderRadius: '2px' }} />
          </div>
        </div>
      )}
      {agreement && (
        <p style={{ fontSize: '0.72rem', color: '#10b981' }}>✅ 理论与历史吻合，信号较可靠</p>
      )}
      {theoretical != null && empirical != null && !agreement && Math.abs(theoretical - empirical) > 15 && (
        <p style={{ fontSize: '0.72rem', color: '#f59e0b' }}>⚠️ 理论与历史差距较大，需额外留意</p>
      )}
    </div>
  );
}

function MetricRow({ label, value, tip, valueColor }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
        {tip ? <Tooltip text={tip}><span>{label}</span></Tooltip> : label}
      </span>
      <span style={{ fontSize: '0.85rem', fontWeight: 600, color: valueColor || 'var(--text-primary)' }}>
        {value}
      </span>
    </div>
  );
}

export default function OptionCard({ option, onClick }) {
  const cfg = STRATEGY_CONFIG[option.strategy] || STRATEGY_CONFIG.sell_put;
  const isSell = option.strategy.startsWith('sell_');
  const thetaDisplay = option.thetaPerDay != null
    ? (isSell
        ? `+$${Math.abs(option.thetaPerDay).toFixed(2)}/天`
        : `-$${Math.abs(option.thetaPerDay).toFixed(2)}/天`)
    : 'N/A';
  const thetaColor = isSell ? '#10b981' : '#ef4444';

  return (
    <div
      className="glass-panel option-card"
      onClick={onClick}
      style={{ padding: '1.25rem', cursor: 'pointer' }}
    >
      {/* ── 头部 ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
            <span style={{ fontSize: '1.6rem', fontWeight: 700, letterSpacing: '-0.02em' }}>{option.symbol}</span>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>${option.currentPrice.toFixed(2)}</span>
          </div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
            到期：{option.expirationDate}（{option.dte} 天后）
          </span>
        </div>
        <span style={{
          background: cfg.bg, color: cfg.color,
          padding: '0.2rem 0.65rem', borderRadius: '999px',
          fontSize: '0.72rem', fontWeight: 700,
          border: `1px solid ${cfg.color}33`,
        }}>
          {cfg.label}
        </span>
      </div>

      {/* ── 财报高危警告 ── */}
      {option.earningsRisk && (
        <div style={{ background: 'rgba(239, 68, 68, 0.2)', color: 'var(--danger-color)', padding: '0.4rem 0.6rem', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.75rem', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
          <span style={{fontSize: '1rem'}}>⚠️</span> 财报高危 (Earnings Before Expiry: {option.earningsDate})
        </div>
      )}

      {/* ── IV Rank ── */}
      <div style={{ marginBottom: '0.75rem' }}>
        <Tooltip text={TIPS.ivRank} width={280}>
          <IVRankBar value={option.ivRank} />
        </Tooltip>
      </div>

      {/* ── 核心数据 4 格 ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.75rem' }}>
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '0.6rem' }}>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>行权价</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>${option.strike.toFixed(2)}</div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '0.6rem' }}>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>权利金（收/付）</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#60a5fa' }}>${option.premium.toFixed(2)}</div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '0.6rem' }}>
          <Tooltip text={TIPS.distancePct}>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>
              {option.strategy === 'sell_put' || option.strategy === 'buy_put' ? '还需下跌才触及' : '还需上涨才到达'}
            </div>
          </Tooltip>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: option.distancePct >= 5 ? '#10b981' : '#f59e0b' }}>
            {option.distancePct.toFixed(1)}%
          </div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '0.6rem' }}>
          <Tooltip text={TIPS.breakEven}>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>盈亏平衡点</div>
          </Tooltip>
          <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>${option.breakEven.toFixed(2)}</div>
        </div>
      </div>

      {/* ── 详细指标行 ── */}
      <div style={{ marginBottom: '0.75rem' }}>
        <MetricRow
          label="年化回报率"
          value={`${option.annualizedReturn.toFixed(1)}%`}
          tip={TIPS.annualizedReturn}
          valueColor="#10b981"
        />
        <MetricRow
          label="最大获利 / 合约"
          value={option.maxProfit != null ? `$${option.maxProfit.toFixed(0)}` : '无限'}
          tip={TIPS.maxProfit}
          valueColor="#10b981"
        />
        <MetricRow
          label="最大亏损 / 合约"
          value={option.maxLoss != null ? `$${option.maxLoss.toFixed(0)}` : '无限'}
          tip={TIPS.maxLoss}
          valueColor="#ef4444"
        />
        <MetricRow
          label="Theta（时间收益/成本）"
          value={thetaDisplay}
          tip={TIPS.theta}
          valueColor={thetaColor}
        />
        <MetricRow
          label="Delta"
          value={option.delta != null ? option.delta.toFixed(3) : 'N/A'}
          tip={TIPS.delta}
        />
        <MetricRow
          label="买卖价差"
          value={option.bidAskSpread != null ? `$${option.bidAskSpread.toFixed(2)} (${option.bidAskSpreadPct}%)` : 'N/A'}
          tip={TIPS.bidAskSpread}
          valueColor={option.bidAskSpreadPct > 10 ? '#f59e0b' : 'var(--text-primary)'}
        />
      </div>

      {/* ── 预期波动范围 ── */}
      <div style={{ marginBottom: '0.75rem', padding: '0.6rem', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
        <Tooltip text={TIPS.expectedMove}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            到期预期波动范围（±1σ，68% 概率）
          </span>
        </Tooltip>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '4px', fontSize: '0.85rem' }}>
          <span style={{ color: '#ef4444' }}>${option.expectedMoveLower?.toFixed(2)}</span>
          <span style={{ flex: 1, height: '2px', background: 'linear-gradient(to right, #ef4444, #10b981)', borderRadius: '1px' }} />
          <span style={{ color: '#10b981' }}>${option.expectedMoveUpper?.toFixed(2)}</span>
        </div>
        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '3px', textAlign: 'center' }}>
          ±{option.expectedMovePct}% · 行权价{' '}
          {option.expectedMoveLower != null && option.strike < option.expectedMoveLower
            ? <span style={{ color: '#10b981' }}>在安全区外 ✅</span>
            : <span style={{ color: '#f59e0b' }}>在波动区间内 ⚠️</span>
          }
        </div>
      </div>

      {/* ── PoP 双显示 ── */}
      <PoPBar theoretical={option.popTheoretical} empirical={option.popEmpirical} />

      <p style={{ marginTop: '0.75rem', fontSize: '0.72rem', color: 'rgba(148,163,184,0.5)', textAlign: 'center' }}>
        点击查看历史验证、损益图和新闻分析 →
      </p>
    </div>
  );
}
