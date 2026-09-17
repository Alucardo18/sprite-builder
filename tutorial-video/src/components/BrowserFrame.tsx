import React from 'react';

interface BrowserFrameProps {
  children: React.ReactNode;
  url?: string;
  title?: string;
}

export const BrowserFrame: React.FC<BrowserFrameProps> = ({
  children,
  url = 'http://localhost:8501/?page=tilesets',
  title = 'sprite-builder · Tileset Builder',
}) => {
  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: '#0e131f',
        borderRadius: 18,
        overflow: 'hidden',
        border: '1px solid rgba(99, 220, 255, 0.22)',
        boxShadow:
          '0 25px 80px rgba(0, 0, 0, 0.85), 0 0 45px rgba(78, 100, 255, 0.15)',
      }}
    >
      {/* macOS Window Topbar */}
      <div
        style={{
          height: 48,
          backgroundColor: '#141c2c',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 18px',
          gap: 16,
          userSelect: 'none',
          position: 'relative',
          zIndex: 10,
        }}
      >
        {/* Window Traffic Lights */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              backgroundColor: '#ff5f56',
              border: '1px solid #e0443e',
            }}
          />
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              backgroundColor: '#ffbd2e',
              border: '1px solid #dea123',
            }}
          />
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              backgroundColor: '#27c93f',
              border: '1px solid #1aab29',
            }}
          />
        </div>

        {/* URL / Title Bar */}
        <div
          style={{
            flex: 1,
            maxWidth: 620,
            margin: '0 auto',
            height: 28,
            backgroundColor: 'rgba(255, 255, 255, 0.06)',
            borderRadius: 7,
            border: '1px solid rgba(255, 255, 255, 0.09)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10,
            padding: '0 12px',
          }}
        >
          <span style={{ fontSize: 11, color: '#57dfbc' }}>🔒</span>
          <span
            style={{
              fontFamily: 'Inter, system-ui, sans-serif',
              fontSize: 12,
              color: '#cbd5e1',
              fontWeight: 500,
              letterSpacing: '0.01em',
            }}
          >
            {url}
          </span>
        </div>

        {/* App Title badge */}
        <div
          style={{
            fontFamily: 'Inter, system-ui, sans-serif',
            fontSize: 11,
            fontWeight: 700,
            color: '#818cf8',
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}
        >
          {title}
        </div>
      </div>

      {/* Main Viewport Content */}
      <div
        style={{
          flex: 1,
          position: 'relative',
          overflow: 'hidden',
          backgroundColor: '#0a0e17',
        }}
      >
        {children}
      </div>
    </div>
  );
};
