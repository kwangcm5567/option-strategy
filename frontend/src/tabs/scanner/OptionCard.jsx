import { useState, useEffect } from 'react';
import Tooltip from '../../components/ui/Tooltip';
import { API_BASE } from '../../hooks/useApi';
import { TIPS } from '../../constants/tooltips';

const STRATEGY_CONFIG = {
  sell_put:  { label: '卖出 Put', color: '#10b981', bg: 'rgba(16,185,129,0.1)'  },
  buy_call:  { label: '买入 Call', color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)' },
  sell_call: { label: '卖出 Call', color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  buy_put:   { label: '买入 Put', color: '#ef4444', bg: 'rgba(239,68,68,0.1)'   },
};

const NEWS_RISK_STYLE = {
  高: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)' },
  中: { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.3)' },
  低: { color: '#10b981', bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.3)' },
};

// ─── AI 推荐逻辑 ─────────────────────────────────────────────────────────────
function getRecommendation(option, newsRisk) {
  const isSell = option.strategy.startsWith('sell_');

  if (option.earningsRisk) {
    return {
      level: 'block',
      text: '到期日跨过财报，IV Crush + 价格跳空风险无法对冲。强烈建议等财报发布后再考虑建仓。',
    };
  }

  const risks = [];
  const pros = [];

  if (option.dividendRisk)           risks.push(`除息日 ${option.exDivDate} 在持仓窗口内，股价将跳空下行`);
  if (option.gapRiskCount >= 6)      risks.push(`高频跳空（过去1年 ${option.gapRiskCount} 次单日跌幅 >5%）`);
  else if (option.gapRiskCount >= 3) risks.push(`中频跳空（${option.gapRiskCount} 次/年）`);
  if (newsRisk?.riskLevel === '高')  risks.push(`新闻情绪高风险${newsRisk.topRiskKeywords?.length ? `（${newsRisk.topRiskKeywords.slice(0,2).join('、')}）` : ''}`);
  else if (newsRisk?.riskLevel === '中') risks.push('新闻情绪偏负面');
  if (option.liquidityScore < 4)     risks.push(`流动性极差（${option.liquidityScore}/10），平仓成本极高`);
  else if (option.liquidityScore < 6) risks.push(`流动性偏弱（${option.liquidityScore}/10）`);
  if (option.bidAskSpreadPct > 15)   risks.push(`买卖价差过宽（${option.bidAskSpreadPct}%）`);
  if (option.distancePct < 3 && isSell) risks.push(`安全边际不足（距行权价仅 ${option.distancePct}%）`);

  if (isSell) {
    if (option.ivRank >= 60)         pros.push(`IV Rank 很高（${option.ivRank}%），卖方时机佳`);
    else if (option.ivRank >= 40)    pros.push(`IV Rank 适中（${option.ivRank}%）`);
    if (option.ivHvRatio >= 1.2)     pros.push(`期权溢价高（IV/HV ${option.ivHvRatio}×），卖方有明显优势`);
    else if (option.ivHvRatio >= 1.05) pros.push(`期权略贵（IV/HV ${option.ivHvRatio}×）`);
    if (option.popEmpirical >= 80)   pros.push(`历史胜率强劲（${option.popEmpirical}%）`);
    else if (option.popEmpirical >= 70) pros.push(`历史胜率良好（${option.popEmpirical}%）`);
    if (option.distancePct >= 10)    pros.push(`安全边际充足（距行权价 ${option.distancePct}%）`);
    if (option.annualizedReturn >= 20) pros.push(`年化回报率高（${option.annualizedReturn}%）`);
    if (option.p50 >= 85)            pros.push(`P50 很高（${option.p50}%），适合 50% 止盈策略`);
    if (option.liquidityScore >= 7)  pros.push('流动性良好，可灵活平仓');
  } else {
    if (option.ivRank <= 25)         pros.push(`IV Rank 低（${option.ivRank}%），买方成本低`);
    if (option.ivHvRatio != null && option.ivHvRatio <= 0.85) pros.push(`期权折价（IV/HV ${option.ivHvRatio}×），买方占优`);
    if (option.popEmpirical >= 40)   pros.push(`历史方向胜率 ${option.popEmpirical}%`);
    if (option.aboveSma50)           pros.push('价格在 50 日均线上方，趋势向上');
    if (option.distancePct <= 5)     pros.push(`接近 ATM（距 ${option.distancePct}%），Delta 较高`);
  }

  const majorRisks = risks.filter(r =>
    r.includes('除息') || r.includes('高频跳空') || r.includes('高风险') || r.includes('极差')
  );

  if (majorRisks.length >= 2) {
    return { level: 'block', text: `多项重大风险并存：${majorRisks.slice(0,2).join('；')}。不建议操作，建议等待条件改善。` };
  }
  if (risks.length >= 3 || majorRisks.length >= 1) {
    const sizeHint = isSell ? '建议仓位缩小至正常的 50%。' : '建议小仓位试探，严格止损。';
    return {
      level: 'caution',
      text: `注意风险：${risks.slice(0,2).join('；')}。${pros.length > 0 ? `优势：${pros[0]}。` : ''}${sizeHint}`,
    };
  }
  if (risks.length >= 1 && pros.length >= 1) {
    return {
      level: 'neutral',
      text: `可操作但需留意：${risks[0]}。支撑点：${pros.slice(0,2).join('、')}。${isSell ? '建议半仓进入，50% 利润时止盈。' : '控制仓位，注意止损。'}`,
    };
  }
  if (pros.length >= 2) {
    return {
      level: 'go',
      text: `${pros.slice(0,2).join('；')}。综合条件良好，${isSell ? '可按正常仓位建仓，目标 50% 权利金时止盈。' : '可建仓，留意大盘趋势配合。'}`,
    };
  }
  return {
    level: 'neutral',
    text: `信号中性，${isSell ? `IV Rank ${option.ivRank}%，历史胜率 ${option.popEmpirical ?? '—'}%。` : `距行权价 ${option.distancePct}%。`}建议等待更明确的条件后再操作。`,
  };
}

// ─── 评分圆环 ─────────────────────────────────────────────────────────────────
function ScoreCircle({ score }) {
  const pct = Math.min(Math.round(score * 100), 99);
  const r = 20;
  const circ = 2 * Math.PI * r;
  const filled = (pct / 100) * circ;
  const color = pct >= 65 ? '#10b981' : pct >= 45 ? '#f59e0b' : '#ef4444';
  return (
    <div style={{ position: 'relative', width: 52, height: 52, flexShrink: 0 }}>
      <svg width="52" height="52" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="26" cy="26" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4" />
        <circle cx="26" cy="26" r={r} fill="none" stroke={color} strokeWidth="4"
          strokeDasharray={`${filled} ${circ}`} strokeLinecap="round" />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 0 }}>
        <span style={{ fontSize: '0.88rem', fontWeight: 800, color, lineHeight: 1.1 }}>{pct}</span>
        <span style={{ fontSize: '0.58rem', color: 'var(--text-secondary)', lineHeight: 1 }}>评分</span>
      </div>
    </div>
  );
}

// ─── IV Rank + IV/HV ──────────────────────────────────────────────────────────
function IVRankBar({ value, ivHvRatio }) {
  const color = value >= 60 ? '#ef4444' : value >= 30 ? '#f59e0b' : '#10b981';
  const label = value >= 60 ? '期权偏贵，卖方有利' : value >= 30 ? '期权正常' : '期权便宜，买方有利';

  let ratioColor = '#f59e0b', ratioLabel = '估值适中';
  if (ivHvRatio != null) {
    if      (ivHvRatio >= 1.2)  { ratioColor = '#10b981'; ratioLabel = `${ivHvRatio}× · 明显偏贵↑卖方优势`; }
    else if (ivHvRatio >= 1.05) { ratioColor = '#10b981'; ratioLabel = `${ivHvRatio}× · 略贵`; }
    else if (ivHvRatio <= 0.80) { ratioColor = '#8b5cf6'; ratioLabel = `${ivHvRatio}× · 明显偏便宜↑买方优势`; }
    else if (ivHvRatio <= 0.95) { ratioColor = '#8b5cf6'; ratioLabel = `${ivHvRatio}× · 略便宜`; }
    else                         { ratioLabel = `${ivHvRatio}× · 估值适中`; }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '3px', color: 'var(--text-secondary)' }}>
        <span>IV Rank</span>
        <span style={{ color }}>{value}% · {label}</span>
      </div>
      <div style={{ height: '5px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${value}%`, background: color, borderRadius: '3px', transition: 'width 0.8s ease' }} />
      </div>
      {ivHvRatio != null && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', marginTop: '5px', color: 'var(--text-secondary)' }}>
          <span>IV / 历史波动率</span>
          <span style={{ color: ratioColor, fontWeight: 600 }}>{ratioLabel}</span>
        </div>
      )}
    </div>
  );
}

// ─── 流动性评分条 ─────────────────────────────────────────────────────────────
function LiquidityBar({ score }) {
  const color = score >= 7 ? '#10b981' : score >= 5 ? '#f59e0b' : '#ef4444';
  const label = score >= 7 ? '流动性良好' : score >= 5 ? '流动性一般' : '流动性差，平仓可能困难';
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '3px', color: 'var(--text-secondary)' }}>
        <span>流动性</span>
        <span style={{ color, fontWeight: 600 }}>{score}/10 · {label}</span>
      </div>
      <div style={{ height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${score * 10}%`, background: color, borderRadius: '2px', transition: 'width 0.8s ease' }} />
      </div>
    </div>
  );
}

// ─── PoP 双显示 ───────────────────────────────────────────────────────────────
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
            <div style={{ height: '100%', width: `${Math.min(empirical, 100)}%`, background: empirical >= 70 ? '#10b981' : '#f59e0b', borderRadius: '2px' }} />
          </div>
        </div>
      )}
      {agreement && <p style={{ fontSize: '0.72rem', color: '#10b981' }}>✅ 理论与历史吻合，信号较可靠</p>}
      {theoretical != null && empirical != null && !agreement && Math.abs(theoretical - empirical) > 15 && (
        <p style={{ fontSize: '0.72rem', color: '#f59e0b' }}>⚠️ 理论与历史差距较大，需额外留意</p>
      )}
    </div>
  );
}

// ─── 关键价位表 ───────────────────────────────────────────────────────────────
function KeyLevels({ option }) {
  const isSell = option.strategy.startsWith('sell_');
  const isPut  = option.strategy.includes('put');

  const rows = [];

  if (isSell && option.p50 != null) {
    const btcTarget = isPut
      ? (option.strike - option.premium / 2).toFixed(2)
      : (option.strike + option.premium / 2).toFixed(2);
    rows.push({ icon: '✅', label: '50% 止盈时股价需高于', price: `$${btcTarget}`, note: `BTC 价格：$${(option.premium / 2).toFixed(2)}`, color: '#10b981' });
  }

  rows.push({ icon: '📍', label: '行权价', price: `$${option.strike.toFixed(2)}`, note: '被行权分界线', color: 'var(--text-primary)' });
  rows.push({ icon: '⚠️', label: '盈亏平衡点', price: `$${option.breakEven.toFixed(2)}`, note: '低于此价开始亏损', color: '#f59e0b' });

  if (option.supportLevel && isPut) {
    const distToSupport = ((option.strike - option.supportLevel) / option.supportLevel * 100).toFixed(1);
    rows.push({
      icon: '🛡️', label: '历史支撑位（20th pct）',
      price: `$${option.supportLevel.toFixed(2)}`,
      note: `行权价高于支撑位 ${distToSupport}%`,
      color: distToSupport > 0 ? '#60a5fa' : '#ef4444',
    });
  }

  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '8px', overflow: 'hidden', marginBottom: '0.75rem' }}>
      <div style={{ padding: '0.4rem 0.6rem', background: 'rgba(255,255,255,0.05)', fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 600, letterSpacing: '0.05em' }}>
        关键价位
      </div>
      {rows.map((r, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.35rem 0.6rem', borderTop: i > 0 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
          <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)' }}>{r.icon} {r.label}</span>
          <div style={{ textAlign: 'right' }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 700, color: r.color }}>{r.price}</span>
            {r.note && <div style={{ fontSize: '0.65rem', color: 'rgba(148,163,184,0.6)' }}>{r.note}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── 推荐框 ───────────────────────────────────────────────────────────────────
function RecommendationBox({ recommendation }) {
  const styles = {
    go:      { bg: 'rgba(16,185,129,0.1)',  border: 'rgba(16,185,129,0.35)',  color: '#6ee7b7', icon: '✅' },
    neutral: { bg: 'rgba(96,165,250,0.08)', border: 'rgba(96,165,250,0.25)',  color: '#93c5fd', icon: '📊' },
    caution: { bg: 'rgba(245,158,11,0.1)',  border: 'rgba(245,158,11,0.35)',  color: '#fcd34d', icon: '⚠️' },
    block:   { bg: 'rgba(239,68,68,0.1)',   border: 'rgba(239,68,68,0.35)',   color: '#fca5a5', icon: '⛔' },
  };
  const s = styles[recommendation.level] || styles.neutral;

  return (
    <div style={{ padding: '0.6rem 0.75rem', background: s.bg, border: `1px solid ${s.border}`, borderRadius: '8px', marginBottom: '0.75rem' }}>
      <div style={{ fontSize: '0.72rem', fontWeight: 700, color: s.color, marginBottom: '0.25rem', letterSpacing: '0.03em' }}>
        {s.icon} AI 建议
      </div>
      <p style={{ fontSize: '0.78rem', color: s.color, lineHeight: 1.55, margin: 0, opacity: 0.9 }}>
        {recommendation.text}
      </p>
    </div>
  );
}

function MetricRow({ label, value, tip, valueColor }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
        {tip ? <Tooltip text={tip}><span>{label}</span></Tooltip> : label}
      </span>
      <span style={{ fontSize: '0.85rem', fontWeight: 600, color: valueColor || 'var(--text-primary)' }}>{value}</span>
    </div>
  );
}

// ─── 机构标准评估 ─────────────────────────────────────────────────────────────
function InstitutionalMetrics({ option }) {
  const stdDist = option.stdDistance;
  const roc = option.roc;
  const ivPrem = option.ivPremium;

  if (stdDist == null && roc == null && ivPrem == null) return null;

  let stdDistColor = '#ef4444', stdDistLabel = '';
  if (stdDist != null) {
    if (stdDist >= 1.5)      { stdDistColor = '#60a5fa'; stdDistLabel = `${stdDist}σ · 保守（超出甜点区）`; }
    else if (stdDist >= 1.2) { stdDistColor = '#10b981'; stdDistLabel = `${stdDist}σ · 最优甜点`; }
    else if (stdDist >= 1.0) { stdDistColor = '#10b981'; stdDistLabel = `${stdDist}σ · 符合机构标准`; }
    else                     { stdDistColor = '#ef4444'; stdDistLabel = `${stdDist}σ · 低于1.0σ最低标准`; }
  }

  let rocColor = 'var(--text-primary)', rocLabel = '';
  if (roc != null) {
    if (roc >= 15 && roc <= 25)  { rocColor = '#10b981'; rocLabel = '甜点 15-25%'; }
    else if (roc >= 10)          { rocColor = '#f59e0b'; rocLabel = '可接受'; }
    else                         { rocColor = '#ef4444'; rocLabel = '偏低'; }
  }

  let ivPremColor = 'var(--text-secondary)', ivPremLabel = '';
  if (ivPrem != null) {
    if (ivPrem >= 30)      { ivPremColor = '#10b981'; ivPremLabel = '卖方优势明显'; }
    else if (ivPrem >= 10) { ivPremColor = '#f59e0b'; ivPremLabel = '轻微优势'; }
    else if (ivPrem >= 0)  { ivPremColor = '#f59e0b'; ivPremLabel = '接近历史波动率'; }
    else                   { ivPremColor = '#8b5cf6'; ivPremLabel = '买方占优'; }
  }

  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '8px', overflow: 'hidden', marginBottom: '0.75rem' }}>
      <div style={{ padding: '0.4rem 0.6rem', background: 'rgba(59,130,246,0.08)', fontSize: '0.72rem', color: '#60a5fa', fontWeight: 600, letterSpacing: '0.05em', borderBottom: '1px solid rgba(59,130,246,0.15)' }}>
        📐 机构标准评估
      </div>
      {stdDist != null && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.35rem 0.6rem' }}>
          <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)' }}>
            σ-距离 <span style={{ fontSize: '0.65rem', opacity: 0.7 }}>（预期波动倍数，甜点 1.2σ）</span>
          </span>
          <span style={{ fontSize: '0.82rem', fontWeight: 700, color: stdDistColor }}>{stdDistLabel || `${stdDist}σ`}</span>
        </div>
      )}
      {roc != null && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.35rem 0.6rem', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
          <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)' }}>
            ROC <span style={{ fontSize: '0.65rem', opacity: 0.7 }}>（权利金/最大亏损 年化，目标 15-25%）</span>
          </span>
          <span style={{ fontSize: '0.82rem', fontWeight: 700, color: rocColor }}>{roc.toFixed(1)}%{rocLabel && ` · ${rocLabel}`}</span>
        </div>
      )}
      {ivPrem != null && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.35rem 0.6rem', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
          <span style={{ fontSize: '0.73rem', color: 'var(--text-secondary)' }}>
            IV溢价 <span style={{ fontSize: '0.65rem', opacity: 0.7 }}>（相对历史波动率，正值卖方有利）</span>
          </span>
          <span style={{ fontSize: '0.82rem', fontWeight: 700, color: ivPremColor }}>
            {ivPrem > 0 ? '+' : ''}{ivPrem.toFixed(1)}%{ivPremLabel && ` · ${ivPremLabel}`}
          </span>
        </div>
      )}
    </div>
  );
}

// ─── 主组件 ───────────────────────────────────────────────────────────────────
export default function OptionCard({ option, onClick }) {
  const [newsRisk, setNewsRisk] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/news/${option.symbol}?strategy=${option.strategy}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d && !cancelled) setNewsRisk(d); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [option.symbol, option.strategy]);

  const cfg    = STRATEGY_CONFIG[option.strategy] || STRATEGY_CONFIG.sell_put;
  const isSell = option.strategy.startsWith('sell_');
  const thetaDisplay = option.thetaPerDay != null
    ? (isSell ? `+$${Math.abs(option.thetaPerDay).toFixed(2)}/天` : `-$${Math.abs(option.thetaPerDay).toFixed(2)}/天`)
    : 'N/A';
  const thetaColor = isSell ? '#10b981' : '#ef4444';

  const gapLabel = option.gapRiskCount >= 6
    ? { text: `🔥 跳空高风险（${option.gapRiskCount}次）`, color: '#ef4444', bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.3)' }
    : option.gapRiskCount >= 3
    ? { text: `⚡ 跳空中等（${option.gapRiskCount}次）`,   color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.3)' }
    : null;

  const recommendation = getRecommendation(option, newsRisk);

  return (
    <div
      className="glass-panel option-card"
      onClick={onClick}
      style={{ padding: '1.25rem', cursor: 'pointer' }}
    >
      {/* ── 头部：标题 + 评分圆环 ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem', gap: '0.5rem' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '1.6rem', fontWeight: 700, letterSpacing: '-0.02em' }}>{option.symbol}</span>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>${option.currentPrice.toFixed(2)}</span>
            <span style={{
              background: cfg.bg, color: cfg.color,
              padding: '0.15rem 0.6rem', borderRadius: '999px',
              fontSize: '0.7rem', fontWeight: 700, border: `1px solid ${cfg.color}33`,
            }}>
              {cfg.label}
            </span>
          </div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
            到期：{option.expirationDate}（{option.dte} 天后）
          </span>
        </div>
        <ScoreCircle score={option.score} />
      </div>

      {/* ── 风险警告：财报 ── */}
      {option.earningsRisk && (
        <div style={{ background: 'rgba(239,68,68,0.15)', color: '#fca5a5', padding: '0.5rem 0.75rem', borderRadius: '8px', fontSize: '0.78rem', fontWeight: 700, display: 'flex', flexDirection: 'column', gap: '0.2rem', marginBottom: '0.4rem', border: '1px solid rgba(239,68,68,0.4)', borderLeft: '4px solid #ef4444' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span>⛔</span> 财报高危 · 到期日跨过财报
          </div>
          <div style={{ fontWeight: 400, fontSize: '0.72rem', color: 'rgba(252,165,165,0.8)' }}>
            财报日 {option.earningsDate} · IV Crush 风险极高，不建议持仓跨过该日期
          </div>
        </div>
      )}

      {/* ── 风险警告：除息 ── */}
      {option.dividendRisk && (
        <div style={{ background: 'rgba(245,158,11,0.12)', color: '#fcd34d', padding: '0.45rem 0.7rem', borderRadius: '8px', fontSize: '0.75rem', fontWeight: 700, display: 'flex', flexDirection: 'column', gap: '0.15rem', marginBottom: '0.4rem', border: '1px solid rgba(245,158,11,0.35)', borderLeft: '4px solid #f59e0b' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span>💰</span> 除息日在持仓窗口内
          </div>
          <div style={{ fontWeight: 400, fontSize: '0.71rem', color: 'rgba(252,211,77,0.8)' }}>
            除息日 {option.exDivDate} · 股价届时将向下跳空，卖 Put 需提高安全边际
          </div>
        </div>
      )}

      {/* ── 小徽标：跳空风险 + 新闻风险 ── */}
      {(gapLabel || newsRisk) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '0.75rem' }}>
          {gapLabel && (
            <span style={{ padding: '0.2rem 0.55rem', borderRadius: '999px', fontSize: '0.72rem', color: gapLabel.color, background: gapLabel.bg, border: `1px solid ${gapLabel.border}` }}>
              {gapLabel.text}
            </span>
          )}
          {newsRisk && (
            <span style={{ padding: '0.2rem 0.55rem', borderRadius: '999px', fontSize: '0.72rem', color: NEWS_RISK_STYLE[newsRisk.riskLevel]?.color, background: NEWS_RISK_STYLE[newsRisk.riskLevel]?.bg, border: `1px solid ${NEWS_RISK_STYLE[newsRisk.riskLevel]?.border}` }}>
              📰 新闻：{newsRisk.riskLevel}{newsRisk.topRiskKeywords?.length > 0 ? ` [${newsRisk.topRiskKeywords.slice(0,2).join('、')}]` : ''}
            </span>
          )}
        </div>
      )}

      {/* ── IV Rank + IV/HV ── */}
      <div style={{ marginBottom: '0.75rem' }}>
        <Tooltip text={TIPS.ivRank} width={280}>
          <IVRankBar value={option.ivRank} ivHvRatio={option.ivHvRatio} />
        </Tooltip>
      </div>

      {/* ── 核心数据 4 格 ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.75rem' }}>
        {[
          { label: '行权价', value: `$${option.strike.toFixed(2)}` },
          { label: '权利金', value: `$${option.premium.toFixed(2)}`, color: '#60a5fa' },
          {
            label: option.strategy === 'sell_put' || option.strategy === 'buy_put' ? '下跌触及距离' : '上涨触及距离',
            value: `${option.distancePct.toFixed(1)}%`,
            color: option.distancePct >= 5 ? '#10b981' : '#f59e0b',
            tip: TIPS.distancePct,
          },
          { label: '盈亏平衡', value: `$${option.breakEven.toFixed(2)}`, tip: TIPS.breakEven },
        ].map(({ label, value, color, tip }) => (
          <div key={label} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '0.6rem' }}>
            {tip
              ? <Tooltip text={tip}><div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>{label}</div></Tooltip>
              : <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>{label}</div>
            }
            <div style={{ fontSize: '1.05rem', fontWeight: 700, color: color || 'var(--text-primary)' }}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── 详细指标 ── */}
      <div style={{ marginBottom: '0.75rem' }}>
        <MetricRow label="年化回报率" value={`${option.annualizedReturn.toFixed(1)}%`} tip={TIPS.annualizedReturn} valueColor="#10b981" />
        {option.p50 != null && (
          <MetricRow label="P50（50% 止盈概率）" value={`${option.p50}%`} valueColor={option.p50 >= 80 ? '#10b981' : '#f59e0b'} />
        )}
        <MetricRow label="最大获利 / 合约" value={option.maxProfit != null ? `$${option.maxProfit.toFixed(0)}` : '无限'} tip={TIPS.maxProfit} valueColor="#10b981" />
        <MetricRow label="最大亏损 / 合约" value={option.maxLoss != null ? `$${option.maxLoss.toFixed(0)}` : '无限'} tip={TIPS.maxLoss} valueColor="#ef4444" />
        <MetricRow label="Theta" value={thetaDisplay} tip={TIPS.theta} valueColor={thetaColor} />
        <MetricRow label="Delta" value={option.delta != null ? option.delta.toFixed(3) : 'N/A'} tip={TIPS.delta} />
        <MetricRow
          label="买卖价差"
          value={option.bidAskSpread != null ? `$${option.bidAskSpread.toFixed(2)} (${option.bidAskSpreadPct}%)` : 'N/A'}
          tip={TIPS.bidAskSpread}
          valueColor={option.bidAskSpreadPct > 10 ? '#f59e0b' : 'var(--text-primary)'}
        />
        {option.capitalRequired != null && (
          <MetricRow label="每张合约占用资金" value={`$${option.capitalRequired.toLocaleString()}`} valueColor="var(--text-secondary)" />
        )}
      </div>

      {/* ── 预期波动范围 ── */}
      <div style={{ marginBottom: '0.75rem', padding: '0.6rem', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
        <Tooltip text={TIPS.expectedMove}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>到期预期波动范围（±1σ，68% 概率）</span>
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

      {/* ── 关键价位表 ── */}
      <KeyLevels option={option} />

      {/* ── 机构标准评估 ── */}
      <InstitutionalMetrics option={option} />

      {/* ── 流动性 ── */}
      {option.liquidityScore != null && (
        <div style={{ marginBottom: '0.75rem' }}>
          <LiquidityBar score={option.liquidityScore} />
        </div>
      )}

      {/* ── PoP ── */}
      <div style={{ marginBottom: '0.75rem' }}>
        <PoPBar theoretical={option.popTheoretical} empirical={option.popEmpirical} />
      </div>

      {/* ── AI 建议 ── */}
      <RecommendationBox recommendation={recommendation} />

      <p style={{ fontSize: '0.7rem', color: 'rgba(148,163,184,0.4)', textAlign: 'center', margin: 0 }}>
        点击查看历史验证、损益图和完整新闻分析 →
      </p>
    </div>
  );
}
