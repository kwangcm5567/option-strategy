export default function LoadingSpinner({ message = '正在加载数据…' }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      minHeight: '40vh', gap: '1rem',
    }}>
      <div className="spinner" />
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>{message}</p>
    </div>
  );
}

export function ErrorBox({ message }) {
  return (
    <div style={{
      padding: '1.25rem 1.5rem',
      borderLeft: '4px solid var(--danger-color)',
      background: 'rgba(239,68,68,0.08)',
      borderRadius: '8px',
      color: '#fca5a5',
      fontSize: '0.9rem',
      lineHeight: '1.6',
    }}>
      ⚠️ {message}
    </div>
  );
}
