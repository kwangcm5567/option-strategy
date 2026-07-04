import { useState, useEffect } from 'react';
import { Search, BarChart2, Briefcase, Calendar, TrendingUp, Layers, DollarSign, GitMerge, Activity, Shield } from 'lucide-react';
import ScannerTab from './tabs/scanner/ScannerTab';
import StrategyTab from './tabs/strategy/StrategyTab';
import SpreadsTab from './tabs/spreads/SpreadsTab';
import PositionsTab from './tabs/positions/PositionsTab';
import RiskTab from './tabs/risk/RiskTab';
import EarningsTab from './tabs/earnings/EarningsTab';
import MarketTab from './tabs/market/MarketTab';
import VolTab from './tabs/vol/VolTab';
import EnhanceTab from './tabs/enhance/EnhanceTab';
import IncomeTab from './tabs/income/IncomeTab';
import useExpiryReminder from './hooks/useExpiryReminder';
import { API_BASE } from './hooks/useApi';
import './index.css';

const TABS = [
  { id: 'scanner',   label: '扫描仪',   icon: Search,      component: ScannerTab   },
  { id: 'spreads',   label: '价差扫描', icon: GitMerge,     component: SpreadsTab   },
  { id: 'strategy',  label: '策略构建', icon: BarChart2,    component: StrategyTab  },
  { id: 'positions', label: '持仓追踪', icon: Briefcase,    component: PositionsTab },
  { id: 'risk',      label: '风险台',   icon: Shield,       component: RiskTab      },
  { id: 'income',    label: '收入分析', icon: DollarSign,   component: IncomeTab    },
  { id: 'enhance',   label: '组合增强', icon: Layers,       component: EnhanceTab   },
  { id: 'vol',       label: '波动率',   icon: Activity,     component: VolTab       },
  { id: 'earnings',  label: '财报雷达', icon: Calendar,     component: EarningsTab  },
  { id: 'market',    label: '市场情绪', icon: TrendingUp,   component: MarketTab    },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('scanner');
  const ActiveComponent = TABS.find(t => t.id === activeTab)?.component ?? ScannerTab;
  useExpiryReminder();

  // 提前唤醒 Render 后端（免费层会休眠），减少首次扫描的冷启动等待
  useEffect(() => {
    fetch(`${API_BASE}/api/health`).catch(() => {});
  }, []);

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
