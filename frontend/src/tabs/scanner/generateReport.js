function getStrategyLabel(strategy) {
  const map = {
    sell_put:  '卖出 Put (CSP)',
    buy_call:  '买入 Call',
    sell_call: '卖出 Call (Covered)',
    buy_put:   '买入 Put',
  };
  return map[strategy] || strategy;
}

function getStrategyColor(strategy) {
  const map = {
    sell_put:  '#059669',
    buy_call:  '#2563eb',
    sell_call: '#d97706',
    buy_put:   '#dc2626',
  };
  return map[strategy] || '#6b7280';
}

function getActionPlan(option) {
  const { strategy, symbol, strike, expiry, premium, dte, currentPrice, winRate, annualizedReturn } = option;
  const perContract = Math.round((premium ?? 0) * 100);
  const wrPct   = winRate != null          ? `${(winRate * 100).toFixed(0)}%`          : 'N/A';
  const annPct  = annualizedReturn != null ? `${(annualizedReturn * 100).toFixed(0)}%` : 'N/A';

  switch (strategy) {
    case 'sell_put':
      return `卖出 ${symbol} $${strike} Put，到期日 ${expiry}（${dte} 天），收取权利金 $${perContract}/张。` +
        `盈亏平衡价 $${((strike ?? 0) - (premium ?? 0)).toFixed(2)}，历史胜率 ${wrPct}，年化回报 ${annPct}。` +
        `目标：股价高于 $${strike} 到期则全赚；50% 止盈时以 $${Math.round((premium ?? 0) * 0.5 * 100)}/张 买回平仓。`;

    case 'buy_call': {
      const breakevenCall = ((strike ?? 0) + (premium ?? 0)).toFixed(2);
      const moveNeeded = currentPrice
        ? `（需涨 ${(((strike ?? 0) + (premium ?? 0) - currentPrice) / currentPrice * 100).toFixed(1)}%）`
        : '';
      return `买入 ${symbol} $${strike} Call，到期日 ${expiry}（${dte} 天），支付权利金 $${perContract}/张。` +
        `盈亏平衡 $${breakevenCall}${moveNeeded}，当前价 $${currentPrice?.toFixed(2) ?? 'N/A'}。` +
        `持有至目标价或权利金翻倍时止盈；跌破 50% 成本时止损。`;
    }

    case 'sell_call':
      return `卖出 ${symbol} $${strike} Call（需持100股标的），到期日 ${expiry}（${dte} 天），收取权利金 $${perContract}/张。` +
        `年化回报 ${annPct}，股价不超过 $${strike} 到期则全赚；` +
        `盈亏平衡 $${((strike ?? 0) + (premium ?? 0)).toFixed(2)}。`;

    case 'buy_put': {
      const breakevenPut = ((strike ?? 0) - (premium ?? 0)).toFixed(2);
      const dropNeeded = currentPrice
        ? `（需跌 ${((currentPrice - ((strike ?? 0) - (premium ?? 0))) / currentPrice * 100).toFixed(1)}%）`
        : '';
      return `买入 ${symbol} $${strike} Put，到期日 ${expiry}（${dte} 天），支付权利金 $${perContract}/张。` +
        `盈亏平衡 $${breakevenPut}${dropNeeded}，当前价 $${currentPrice?.toFixed(2) ?? 'N/A'}。` +
        `持有至目标价或权利金翻倍时止盈；跌破 50% 成本时止损。`;
    }

    default:
      return `${strategy} ${symbol} $${strike}（${expiry}），权利金 $${perContract}/张。`;
  }
}

export function generateReport(options, { scanTime, filters } = {}) {
  const now = new Date();
  const reportDate = now.toLocaleDateString('zh-CN', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
  });
  const reportTime = scanTime || now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

  const tableRows = options.map((opt, i) => {
    const color = getStrategyColor(opt.strategy);
    const wr = opt.winRate != null ? `${(opt.winRate * 100).toFixed(0)}%` : '—';
    const ann = opt.annualizedReturn != null ? `${(opt.annualizedReturn * 100).toFixed(0)}%` : '—';
    const wrColor = opt.winRate != null && opt.winRate >= 0.75 ? '#059669' : '#d97706';
    return `
      <tr>
        <td style="text-align:center;font-weight:700;color:#374151">${i + 1}</td>
        <td style="font-weight:800;color:#111;font-size:1rem">${opt.symbol}</td>
        <td><span style="background:${color}18;color:${color};border:1px solid ${color}40;padding:2px 8px;border-radius:4px;font-size:0.78rem;font-weight:700;white-space:nowrap">${getStrategyLabel(opt.strategy)}</span></td>
        <td style="text-align:right;font-weight:700">$${opt.strike}</td>
        <td style="text-align:right">$${Math.round((opt.premium ?? 0) * 100)}/张</td>
        <td style="text-align:center;white-space:nowrap">${opt.expiry ?? '—'}</td>
        <td style="text-align:center">${opt.dte ?? '—'} 天</td>
        <td style="text-align:center;font-weight:700;color:${wrColor}">${wr}</td>
        <td style="text-align:center;font-weight:700;color:#2563eb">${ann}</td>
        <td style="text-align:center">${opt.ivRank != null ? opt.ivRank.toFixed(0) + '%' : '—'}</td>
      </tr>`;
  }).join('');

  const detailCards = options.map((opt, i) => {
    const color = getStrategyColor(opt.strategy);
    const actionPlan = getActionPlan(opt);
    const earningsWarn = opt.earningsDate
      ? `<div style="margin-top:0.75rem;padding:0.5rem 0.85rem;background:#fffbeb;border:1px solid #fcd34d;border-radius:6px;color:#92400e;font-size:0.82rem">
           ⚠️ 财报日 ${opt.earningsDate}${opt.earningsRisk ? ' — 到期前有财报，IV Crush 风险高！请谨慎' : ''}
         </div>`
      : '';
    const deltaStr  = opt.delta != null ? `<div style="${kpiStyle}"><div style="${kpiLabelStyle}">Delta</div><div style="${kpiValStyle}">${opt.delta.toFixed(2)}</div></div>` : '';
    const priceStr  = opt.currentPrice != null ? `<div style="${kpiStyle}"><div style="${kpiLabelStyle}">当前股价</div><div style="${kpiValStyle}">$${opt.currentPrice.toFixed(2)}</div></div>` : '';
    const sigmaStr  = opt.sigma != null ? `<div style="${kpiStyle}"><div style="${kpiLabelStyle}">σ 距离</div><div style="${kpiValStyle}">${opt.sigma.toFixed(2)}σ</div></div>` : '';
    return `
      <div style="page-break-inside:avoid;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:1.25rem 1.5rem;margin-bottom:1rem;border-left:4px solid ${color}">
        <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;margin-bottom:0.85rem">
          <span style="font-size:1.3rem;font-weight:900;color:#111">${i + 1}. ${opt.symbol}</span>
          <span style="background:${color}18;color:${color};border:1px solid ${color}40;padding:3px 10px;border-radius:6px;font-size:0.85rem;font-weight:700">${getStrategyLabel(opt.strategy)}</span>
          ${opt.earningsRisk ? '<span style="background:#fef2f2;color:#dc2626;border:1px solid #fca5a5;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:700">⚠ 财报高危</span>' : ''}
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(145px,1fr));gap:0.55rem;margin-bottom:0.9rem">
          <div style="${kpiStyle}"><div style="${kpiLabelStyle}">行权价</div><div style="${kpiValStyle}">$${opt.strike}</div></div>
          <div style="${kpiStyle}"><div style="${kpiLabelStyle}">权利金</div><div style="${kpiValStyle}">$${(opt.premium ?? 0).toFixed(2)}/股（$${Math.round((opt.premium ?? 0) * 100)}/张）</div></div>
          <div style="${kpiStyle}"><div style="${kpiLabelStyle}">到期日 / DTE</div><div style="${kpiValStyle}">${opt.expiry ?? '—'} / ${opt.dte ?? '—'} 天</div></div>
          <div style="${kpiStyle}"><div style="${kpiLabelStyle}">历史胜率</div><div style="font-weight:700;font-size:0.92rem;color:${opt.winRate != null && opt.winRate >= 0.75 ? '#059669' : '#d97706'}">${opt.winRate != null ? (opt.winRate * 100).toFixed(0) + '%' : '—'}</div></div>
          <div style="${kpiStyle}"><div style="${kpiLabelStyle}">年化回报</div><div style="font-weight:700;font-size:0.92rem;color:#2563eb">${opt.annualizedReturn != null ? (opt.annualizedReturn * 100).toFixed(0) + '%' : '—'}</div></div>
          <div style="${kpiStyle}"><div style="${kpiLabelStyle}">IV Rank</div><div style="${kpiValStyle}">${opt.ivRank != null ? opt.ivRank.toFixed(0) + '%' : '—'}</div></div>
          ${deltaStr}${priceStr}${sigmaStr}
        </div>
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:0.75rem 1rem;color:#166534;font-size:0.87rem;line-height:1.65">
          <strong>📋 交易计划：</strong>${actionPlan}
        </div>
        ${earningsWarn}
      </div>`;
  }).join('');

  const filterBadge = filters
    ? `<div style="display:inline-block;background:rgba(99,102,241,0.25);border:1px solid rgba(99,102,241,0.4);color:#c7d2fe;padding:3px 12px;border-radius:999px;font-size:0.8rem;font-weight:600;margin-top:0.5rem">
         策略：${filters.strategies?.join(' / ') || '全部'} · DTE ${filters.dteMin}–${filters.dteMax} 天 · 最低 IV Rank ${filters.minIvRank}%
       </div>`
    : '';

  return `<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alpha Options 每日报告 — ${reportDate}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f1f5f9;color:#111;padding:2rem}
h2{font-size:1.05rem;font-weight:700;color:#111;margin-bottom:0.75rem}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.07)}
th{background:#1e293b;color:#f1f5f9;font-size:0.76rem;font-weight:700;padding:0.6rem 0.75rem;text-align:center;white-space:nowrap}
td{padding:0.6rem 0.75rem;border-bottom:1px solid #f1f5f9;font-size:0.86rem}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f8fafc}
.section{margin-bottom:2rem}
@media print{
  body{background:#fff;padding:0.75rem}
  .header{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  th{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
</style>
</head>
<body>
<div style="background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);color:#fff;border-radius:14px;padding:1.5rem 2rem;margin-bottom:1.75rem" class="header">
  <div style="font-size:1.7rem;font-weight:900;letter-spacing:-0.5px">📊 Alpha Options 每日扫描报告</div>
  <div style="color:#94a3b8;margin-top:0.35rem;font-size:0.88rem">报告日期：${reportDate} &nbsp;·&nbsp; 扫描时间：${reportTime} &nbsp;·&nbsp; 共 ${options.length} 个交易机会</div>
  ${filterBadge}
</div>

<div class="section">
  <h2>📋 快速参考一览</h2>
  <table>
    <thead>
      <tr><th>#</th><th>标的</th><th>策略</th><th>行权价</th><th>权利金</th><th>到期日</th><th>DTE</th><th>历史胜率</th><th>年化回报</th><th>IV Rank</th></tr>
    </thead>
    <tbody>${tableRows}</tbody>
  </table>
</div>

<div class="section">
  <h2>📌 逐项交易计划</h2>
  ${detailCards}
</div>

<div style="text-align:center;color:#9ca3af;font-size:0.72rem;margin-top:2rem;padding-top:1rem;border-top:1px solid #e5e7eb">
  由 Alpha Options Strategy 生成 &nbsp;·&nbsp; ${reportDate} &nbsp;·&nbsp; 本报告仅供参考，不构成投资建议
</div>
</body>
</html>`;
}

const kpiStyle     = 'background:#f8fafc;border-radius:6px;padding:0.45rem 0.7rem';
const kpiLabelStyle = 'font-size:0.68rem;color:#6b7280;margin-bottom:2px';
const kpiValStyle   = 'font-weight:700;font-size:0.92rem;color:#111';
