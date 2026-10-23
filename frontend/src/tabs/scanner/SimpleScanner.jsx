import { useState } from 'react';
import { RefreshCw, ArrowRight } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import './SimpleScanner.css';

/** @param {number} value */
const dollars = (value) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 2,
}).format(value);

/** @param {{ endpoint: string }} props */
function Results({ endpoint }) {
  const { data, loading, error, refetch } = useApi(endpoint, { timeout: 180_000 });
  return (
    <section aria-label="简单模式结果" aria-busy={loading}>
      <div className="simple-results-heading">
        <h3>候选观察清单</h3>
        <button type="button" onClick={() => refetch(`${endpoint}&force_refresh=true`)} disabled={loading}>
          <RefreshCw size={14} /> {loading ? '扫描中…' : '刷新报价'}
        </button>
      </div>
      {loading && <p role="status" className="simple-notice">正在检查 3 只 ETF 的报价与成本，请稍候…</p>}
      {error && <p role="alert" className="simple-notice">扫描失败：{error}。请重试，当前没有可用结果。</p>}
      {!loading && !error && data && (
        <>
          {data.data.length === 0 ? (
            <div className="simple-empty" role="status">
              <span>今天可以不交易</span>
              <h3>没有符合条件的合约</h3>
              <p>报价可能缺失，或合约未通过现金上限、价差、Delta 与成本筛选。保留现金，稍后再检查。</p>
            </div>
          ) : (
            <>
              <p className="simple-caption">每只 ETF 最多 1 个候选；先选 |Delta| 最接近 0.20，再比较价差与净权利金比例。这不是盈利排名。</p>
              <div className="simple-candidates">
                {data.data.map((option) => (
                  <article className="simple-candidate" key={`${option.symbol}-${option.expirationDate}-${option.strike}`}>
                    <header>
                      <div><span className="simple-eyebrow">现金担保 PUT · 每张 100 股</span><h3>{option.symbol} <span>${option.strike}</span></h3></div>
                      <span className="simple-dte">{option.dte} 天</span>
                    </header>
                    <p className="simple-caption">到期 {option.expirationDate} · 标的 {dollars(option.currentPrice)}</p>
                    <div className="simple-credit"><span>扣除预留成本后的权利金</span><strong>{dollars(option.netCredit)}</strong><small>仅当期权归零时全部保留 · 本期 {option.netReturnPct}%</small></div>
                    <dl>
                      <div><dt>必须预留的现金</dt><dd>{dollars(option.capitalRequired)}</dd></div>
                      <div><dt>到期盈亏平衡价（含成本）</dt><dd>{dollars(option.netBreakEven)}</dd></div>
                      <div><dt>标的归零时损失（含成本）</dt><dd className="simple-loss">{dollars(option.netMaxLoss)}</dd></div>
                      <div><dt>往返费用 + 滑点预留</dt><dd>{dollars(option.estimatedRoundTripCosts)}</dd></div>
                    </dl>
                    <details>
                      <summary>报价与退出参考</summary>
                      <p>Bid {dollars(option.bid)} / Ask {dollars(option.ask)} · 价差 {option.bidAskSpreadPct}% · Delta {option.delta} · 未平仓 {option.openInterest}</p>
                      <p>若买回价降至 {dollars(option.closeTarget)}，扣除预留成本后利润约 {dollars(option.targetNetProfit)}。这是约半数权利金的退出参考，未验证为最优规则。</p>
                      <p>到期前检查是否平仓或准备接股；滚仓会实现旧仓盈亏并开启新风险，不能消除损失。</p>
                    </details>
                    <footer>数据源 {option.source === 'cboe' ? 'CBOE（延迟）' : 'Yahoo Finance'} · 下单前核对券商报价</footer>
                  </article>
                ))}
              </div>
            </>
          )}
          <p className="simple-caption">{data.cached ? '使用 5 分钟内的扫描缓存。' : '本次扫描完成。'} 数据源可能延迟或保留收盘报价；有效 Bid / Ask 不代表实时可成交。</p>
        </>
      )}
    </section>
  );
}

export default function SimpleScanner() {
  const [budget, setBudget] = useState('');
  const [fee, setFee] = useState('0.65');
  const [slippage, setSlippage] = useState('0.01');
  const [endpoint, setEndpoint] = useState('/api/scan?profile=simple&dte_min=30&dte_max=45');

  /** @param {import('react').FormEvent<HTMLFormElement>} event */
  const apply = (event) => {
    event.preventDefault();
    const params = new URLSearchParams({
      profile: 'simple', dte_min: '30', dte_max: '45',
      max_capital: budget || '0', fee_per_contract: fee, slippage_per_share: slippage,
    });
    setEndpoint(`/api/scan?${params}`);
  };

  return (
    <div className="simple-scanner">
      <section className="simple-intro">
        <span className="simple-eyebrow">更少选择 · 看清成本 · 允许空仓</span>
        <h2>先看现金，再看权利金。</h2>
        <p>只筛选 SPY / QQQ / IWM 的现金担保 Put。仅适合愿意按行权价买入 100 股的人；三只 ETF 都有股票市场风险。</p>
        <div className="simple-rules"><span>30–45 天到期</span><span>|Delta| 0.15–0.30</span><span>价差 ≤ 中间价 10%</span><span>未平仓 ≥ 100</span></div>
      </section>
      <form className="simple-controls" onSubmit={apply}>
        <label>单笔可用现金上限（美元）<input aria-label="单笔可用现金上限" type="number" min="0" step="100" placeholder="留空：只看资金要求" value={budget} onChange={event => setBudget(event.target.value)} /></label>
        <label>每张单边费用（美元）<input aria-label="每张单边费用" type="number" min="0" max="100" step="0.01" required value={fee} onChange={event => setFee(event.target.value)} /></label>
        <label>每股单边滑点预留（美元）<input aria-label="每股单边滑点预留" type="number" min="0" max="10" step="0.01" required value={slippage} onChange={event => setSlippage(event.target.value)} /></label>
        <button className="simple-apply" type="submit">应用条件 <ArrowRight size={16} /></button>
        <p>费用默认值仅为示例，请按券商收费修改。现金上限按每张合约筛选，不会读取或扣除现有持仓，也不代表可以同时买入所有候选。</p>
      </form>
      <Results key={endpoint} endpoint={endpoint} />
      <p className="simple-footnote">这些是待验证的筛选规则。当前没有历史期权成交数据来证明净收益或最大回撤；股价历史触及率不等于策略胜率。</p>
    </div>
  );
}
