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

const TAB_GROUPS = [
  {
    label: '找机会',
    tabs: [
      { id: 'scanner',   label: '扫描仪',   icon: Search,     component: ScannerTab   },
      { id: 'spreads',   label: '价差扫描', icon: GitMerge,   component: SpreadsTab   },
      { id: 'strategy',  label: '策略构建', icon: BarChart2,  component: StrategyTab  },
    ],
  },
  {
    label: '管持仓',
    tabs: [
      { id: 'positions', label: '持仓追踪', icon: Briefcase,  component: PositionsTab },
      { id: 'risk',      label: '风险台',   icon: Shield,     component: RiskTab      },
      { id: 'income',    label: '收入分析', icon: DollarSign, component: IncomeTab    },
      { id: 'enhance',   label: '组合增强', icon: Layers,     component: EnhanceTab   },
    ],
  },
  {
    label: '看市场',
    tabs: [
      { id: 'vol',       label: '波动率',   icon: Activity,   component: VolTab       },
      { id: 'earnings',  label: '财报雷达', icon: Calendar,   component: EarningsTab  },
      { id: 'market',    label: '市场情绪', icon: TrendingUp, component: MarketTab    },
    ],
  },
];

const TABS = TAB_GROUPS.flatMap(g => g.tabs);

// URL hash（#/scanner）→ tab id，刷新/分享链接/前进后退都能保住状态
function tabFromHash() {
  const id = window.location.hash.replace(/^#\/?/, '');
  return TABS.some(t => t.id === id) ? id : 'scanner';
}

export default function App() {
  const [activeTab, setActiveTab] = useState(tabFromHash);
  const ActiveComponent = TABS.find(t => t.id === activeTab)?.component ?? ScannerTab;
  useExpiryReminder();

  useEffect(() => {
    const onHashChange = () => setActiveTab(tabFromHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const selectTab = (id) => {
    window.location.assign(`#/${id}`);   // 触发 hashchange → setActiveTab
  };

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

      {/* ── Tab 导航（三组：找机会 / 管持仓 / 看市场）── */}
      <nav style={{
        display: 'flex', gap: '0.3rem', marginBottom: '2rem', alignItems: 'flex-end',
        borderBottom: '1px solid var(--card-border)', paddingBottom: '0',
        overflowX: 'auto',
      }}>
        {TAB_GROUPS.map((group, gi) => (
          <div key={group.label} style={{ display: 'flex', alignItems: 'flex-end', gap: '0.3rem' }}>
            {gi > 0 && (
              <div style={{ width: 1, height: '1.6rem', background: 'var(--card-border)', margin: '0 0.5rem 0.55rem' }} />
            )}
            <span style={{
              fontSize: '0.68rem', color: 'var(--text-secondary)', opacity: 0.7,
              padding: '0 0.2rem 0.75rem 0.1rem', whiteSpace: 'nowrap', letterSpacing: '0.05em',
            }}>
              {group.label}
            </span>
            {group.tabs.map(({ id, label, icon: Icon }) => {
              const active = id === activeTab;
              return (
                <button
                  key={id}
                  onClick={() => selectTab(id)}
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
          </div>
        ))}
      </nav>

      {/* ── 内容区 ── */}
      <main>
        <ActiveComponent />
      </main>
    </div>
  );
}
