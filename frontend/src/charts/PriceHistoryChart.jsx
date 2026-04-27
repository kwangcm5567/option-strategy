import {
  ResponsiveContainer, ComposedChart, Line, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
} from 'recharts';

export default function PriceHistoryChart({ chartData, strike, expectedUpper, expectedLower }) {
  if (!chartData?.length) return null;

  const data = chartData.map((d, i) => ({
    ...d,
    upperBand: i >= chartData.length - 30 ? expectedUpper : null,
    lowerBand: i >= chartData.length - 30 ? expectedLower : null,
  }));

  // 只保留每隔约 60 个数据点的日期，避免 X 轴过密
  const tickIndices = new Set();
  const step = Math.max(1, Math.floor(data.length / 6));
  for (let i = 0; i < data.length; i += step) tickIndices.add(data[i].date);

  return (
    <div>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
        蓝线 = 历史收盘价 &nbsp;·&nbsp; 橙虚线 = 行权价 &nbsp;·&nbsp; 绿色区域 = 到期前 ±1σ 预期波动范围
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data} margin={{ top: 16, right: 16, left: 12, bottom: 32 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />

          <XAxis
            dataKey="date"
            stroke="rgba(148,163,184,0.5)"
            tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
            tickLine={false}
            interval="preserveStartEnd"
            ticks={[...tickIndices]}
            angle={-30}
            textAnchor="end"
            height={48}
          />

          <YAxis
            domain={['auto', 'auto']}
            stroke="rgba(148,163,184,0.5)"
            tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
            tickLine={false}
            tickFormatter={v => `$${v.toFixed(0)}`}
            width={56}
          />

          <Tooltip
            contentStyle={{
              background: '#1e293b',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '8px',
              fontSize: '0.82rem',
            }}
            labelStyle={{ color: 'var(--text-secondary)', marginBottom: 4 }}
            formatter={(val, name) => {
              if (name === 'upperBand') return [`$${val?.toFixed(2)}`, '预期上限 (+1σ)'];
              if (name === 'lowerBand') return [`$${val?.toFixed(2)}`, '预期下限 (-1σ)'];
              return [`$${val?.toFixed(2)}`, '收盘价'];
            }}
          />

          {strike && (
            <ReferenceLine
              y={strike}
              stroke="#f59e0b"
              strokeDasharray="5 4"
              strokeWidth={1.5}
              label={{
                value: `行权价 $${strike}`,
                fill: '#f59e0b',
                fontSize: 11,
                position: 'insideTopLeft',
                offset: 6,
                dy: -14,
              }}
            />
          )}

          {expectedUpper && (
            <Area
              dataKey="upperBand"
              stroke="rgba(16,185,129,0.5)"
              fill="rgba(16,185,129,0.1)"
              dot={false} activeDot={false} connectNulls={false}
            />
          )}
          {expectedLower && (
            <Area
              dataKey="lowerBand"
              stroke="rgba(16,185,129,0.5)"
              fill="rgba(16,185,129,0.1)"
              dot={false} activeDot={false} connectNulls={false}
            />
          )}

          <Line
            type="monotone"
            dataKey="price"
            stroke="#60a5fa"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#60a5fa' }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
