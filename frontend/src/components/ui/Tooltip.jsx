import { useState, useRef, useCallback } from 'react';

/**
 * 金融术语 Tooltip — 使用 position:fixed 避免被父层 overflow:hidden 裁切
 */
export default function Tooltip({ text, children, width = 260 }) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ x: 0, above: true, anchorY: 0 });
  const btnRef = useRef(null);
  const timerRef = useRef(null);

  const calcPos = useCallback(() => {
    if (!btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    const above = rect.top > 220;
    // 水平方向防止超出屏幕边缘
    const rawX = rect.left + rect.width / 2;
    const x = Math.min(Math.max(width / 2 + 8, rawX), window.innerWidth - width / 2 - 8);
    setPos({
      x,
      above,
      anchorY: above
        ? window.innerHeight - rect.top + 8   // 从视口底部量，放在按钮上方
        : rect.bottom + 8,                      // 从视口顶部量，放在按钮下方
    });
  }, [width]);

  const show = () => { clearTimeout(timerRef.current); calcPos(); setVisible(true); };
  const hide = () => { timerRef.current = setTimeout(() => setVisible(false), 150); };
  const toggle = (e) => {
    e.stopPropagation();
    if (!visible) calcPos();
    setVisible(v => !v);
  };

  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
      {children}
      <button
        ref={btnRef}
        onMouseEnter={show}
        onMouseLeave={hide}
        onClick={toggle}
        style={{
          background: 'none', border: 'none', padding: '0 2px',
          cursor: 'help', color: 'rgba(148,163,184,0.7)',
          fontSize: '0.7rem', lineHeight: 1,
          display: 'inline-flex', alignItems: 'center',
          flexShrink: 0,
        }}
        aria-label="查看说明"
      >
        ⓘ
      </button>

      {visible && (
        <div
          onMouseEnter={show}
          onMouseLeave={hide}
          style={{
            position: 'fixed',
            left: `${pos.x}px`,
            ...(pos.above
              ? { bottom: `${pos.anchorY}px` }
              : { top: `${pos.anchorY}px` }),
            transform: 'translateX(-50%)',
            width: `${width}px`,
            maxWidth: 'calc(100vw - 32px)',
            background: '#1e293b',
            border: '1px solid rgba(96,165,250,0.3)',
            borderRadius: '10px',
            padding: '0.75rem 1rem',
            fontSize: '0.78rem',
            lineHeight: '1.7',
            color: '#cbd5e1',
            zIndex: 99999,
            whiteSpace: 'pre-line',
            boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
            pointerEvents: 'auto',
          }}
        >
          {text}
          {/* 小三角箭头 */}
          <div style={{
            position: 'absolute',
            ...(pos.above ? { top: '100%' } : { bottom: '100%' }),
            left: '50%',
            transform: 'translateX(-50%)',
            border: '6px solid transparent',
            ...(pos.above
              ? { borderTopColor: '#1e293b' }
              : { borderBottomColor: '#1e293b' }),
          }} />
        </div>
      )}
    </span>
  );
}
