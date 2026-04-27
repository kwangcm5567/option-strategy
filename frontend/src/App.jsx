import { useState } from 'react';
import { Search, BarChart2, Briefcase, Calendar, TrendingUp } from 'lucide-react';
import ScannerTab from './tabs/scanner/ScannerTab';
import StrategyTab from './tabs/strategy/StrategyTab';
import PositionsTab from './tabs/positions/PositionsTab';
import EarningsTab from './tabs/earnings/EarningsTab';
import MarketTab from './tabs/market/MarketTab';
import './index.css';

const TABS = [
  { id: 'scanner',   label: '扫描仪',   icon: Search,    component: ScannerTab   },
  { id: 'strategy',  label: '策略构建', icon: BarChart2,  component: StrategyTab  },
  { id: 'positions', label: '持仓追踪', icon: Briefcase,  component: PositionsTab },
  { id: 'earnings',  label: '财报雷达', icon: Calendar,   component: EarningsTab  },
  { id: 'market',    label: '市场情绪', icon: TrendingUp, component: MarketTab    },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('scanner');
  const ActiveComponent = TABS.find(t => t.id === activeTab)?.component ?? ScannerTab;

  return (
    <div className="app-container">
      <header className="header">
        <h1 className="text-gradient">Alpha Options Strategy</h1>
        <p>专业期权分析 · 三岁可懂的白话注释 · 点击 ⓘ 随时查看说明</p>
      </header>

      {/* ── Tab 导航 ── */}
      <nav style={{
        display: 'flex', gap: '0.3rem', marginBottom: '2rem',
        borderBottom: '1px solid var(--card-border)', paddingBottom: '0',
        overflowX: 'auto',
      }}>
        {TABS.map(({ id, label, icon: Icon }) => {
          const active = id === activeTab;
          return (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.4rem',
                padding: '0.65rem 1.1rem',
                background: 'transparent',
                border: 'none',
                borderBottom: active ? '2px solid var(--accent-color)' : '2px solid transparent',
                color: active ? 'var(--accent-color)' : 'var(--text-secondary)',
                cursor: 'pointer',
                fontWeight: active ? 700 : 400,
                fontSize: '0.88rem',
                whiteSpace: 'nowrap',
                transition: 'all 0.2s ease',
                marginBottom: '-1px',
              }}
            >
              <Icon size={16} />
              {label}
            </button>
          );
        })}
      </nav>

      {/* ── 内容区 ── */}
      <main>
        <ActiveComponent />
      </main>
    </div>
  );
}
