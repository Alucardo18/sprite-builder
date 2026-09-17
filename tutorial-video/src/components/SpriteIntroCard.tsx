import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

export const SpriteIntroCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 90 },
  });

  const subtitleOpacity = interpolate(frame, [35, 65], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const badgesOpacity = interpolate(frame, [65, 95], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const floatY = Math.sin(frame / 35) * 6;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        transform: `translateY(${floatY}px)`,
        maxWidth: 1200,
        padding: '0 40px',
      }}
    >
      {/* Category Pill */}
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 10,
          backgroundColor: 'rgba(87, 223, 188, 0.12)',
          border: '1px solid rgba(87, 223, 188, 0.4)',
          borderRadius: 999,
          padding: '8px 22px',
          color: '#57dfbc',
          fontSize: 16,
          fontWeight: 700,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          marginBottom: 24,
          opacity: Math.min(1, frame / 20),
        }}
      >
        <span>⚔️</span>
        <span>Pipeline de Animación 2D · Sprite Builder</span>
      </div>

      {/* Main Title */}
      <h1
        style={{
          fontSize: 82,
          fontWeight: 900,
          color: '#ffffff',
          lineHeight: 1.05,
          letterSpacing: '-0.03em',
          margin: 0,
          transform: `scale(${interpolate(titleProgress, [0, 1], [0.85, 1])})`,
          opacity: titleProgress,
          background: 'linear-gradient(135deg, #ffffff 40%, #57dfbc 80%, #ff6898 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
        }}
      >
        Flujo Completo de Sheet Studio
      </h1>

      {/* Subtitle */}
      <p
        style={{
          fontSize: 27,
          color: '#94a3b8',
          margin: '24px 0 0 0',
          maxWidth: 950,
          lineHeight: 1.45,
          opacity: subtitleOpacity,
        }}
      >
        Aprende a limpiar <strong style={{ color: '#57dfbc' }}>fondos</strong>, preparar{' '}
        <strong style={{ color: '#ffb347' }}>poses</strong>, estabilizar con{' '}
        <strong style={{ color: '#ff6898' }}>alineación multi-anchor</strong> y{' '}
        <strong style={{ color: '#38bdf8' }}>exportar para motores</strong> sin deformar píxeles.
      </p>

      {/* Badges Flow */}
      <div
        style={{
          display: 'flex',
          gap: 16,
          marginTop: 44,
          opacity: badgesOpacity,
          flexWrap: 'wrap',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            border: '1px solid rgba(87, 223, 188, 0.3)',
            borderRadius: 12,
            padding: '12px 20px',
            color: '#e2e8f0',
            fontSize: 18,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <span>🧹</span> 1. Remoción de fondo
        </div>
        <div
          style={{
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            border: '1px solid rgba(255, 179, 71, 0.3)',
            borderRadius: 12,
            padding: '12px 20px',
            color: '#e2e8f0',
            fontSize: 18,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <span>📐</span> 2. Preparar poses
        </div>
        <div
          style={{
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            border: '1px solid rgba(255, 104, 152, 0.3)',
            borderRadius: 12,
            padding: '12px 20px',
            color: '#e2e8f0',
            fontSize: 18,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <span>🎯</span> 3. Multi-anchor
        </div>
        <div
          style={{
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            border: '1px solid rgba(56, 189, 248, 0.3)',
            borderRadius: 12,
            padding: '12px 20px',
            color: '#e2e8f0',
            fontSize: 18,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <span>📦</span> 4. Cortes y Export
        </div>
      </div>
    </div>
  );
};
