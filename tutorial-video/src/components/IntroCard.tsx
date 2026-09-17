import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

export const IntroCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleProgress = spring({
    frame,
    fps,
    config: { damping: 13, mass: 0.8 },
  });

  const subtitleProgress = spring({
    frame: frame - 20,
    fps,
    config: { damping: 14, mass: 0.9 },
  });

  const badgesProgress = spring({
    frame: frame - 40,
    fps,
    config: { damping: 15, mass: 1 },
  });

  const fadeOut = interpolate(frame, [200, 235], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const glowPulse = interpolate(
    Math.sin(frame / 15),
    [-1, 1],
    [0.4, 0.85]
  );

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        backgroundColor: '#070b14',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 500,
        opacity: fadeOut,
        fontFamily: 'Inter, system-ui, sans-serif',
        overflow: 'hidden',
      }}
    >
      {/* Background ambient lighting */}
      <div
        style={{
          position: 'absolute',
          width: 700,
          height: 700,
          borderRadius: '50%',
          background:
            'radial-gradient(circle, rgba(16, 185, 129, 0.22) 0%, rgba(59, 130, 246, 0.15) 50%, transparent 75%)',
          filter: 'blur(70px)',
          transform: `scale(${glowPulse})`,
        }}
      />

      {/* Main Title Badge */}
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 10,
          padding: '6px 18px',
          borderRadius: 999,
          backgroundColor: 'rgba(255, 255, 255, 0.06)',
          border: '1px solid rgba(255, 255, 255, 0.14)',
          marginBottom: 24,
          opacity: titleProgress,
          transform: `translateY(${interpolate(titleProgress, [0, 1], [30, 0])}px)`,
        }}
      >
        <span style={{ fontSize: 16 }}>🌿</span>
        <span
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: '#34d399',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          Guía de Terrenos Orgánicos · Sprite Builder
        </span>
      </div>

      {/* Title */}
      <h1
        style={{
          fontSize: 68,
          fontWeight: 900,
          margin: 0,
          letterSpacing: '-0.04em',
          background: 'linear-gradient(135deg, #ffffff 30%, #6ee7b7 70%, #38bdf8 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          textAlign: 'center',
          lineHeight: 1.15,
          opacity: titleProgress,
          transform: `scale(${interpolate(titleProgress, [0, 1], [0.85, 1])})`,
        }}
      >
        Ecosistemas con Blob 47
      </h1>

      {/* Subtitle */}
      <p
        style={{
          fontSize: 23,
          fontWeight: 500,
          color: '#94a3b8',
          margin: '16px 0 36px',
          textAlign: 'center',
          maxWidth: 820,
          opacity: subtitleProgress,
          transform: `translateY(${interpolate(subtitleProgress, [0, 1], [20, 0])}px)`,
        }}
      >
        Aprende a conectar <strong style={{ color: '#34d399' }}>Pasto sobre Tierra</strong>, <strong style={{ color: '#eab308' }}>Tierra sobre Agua</strong> y <strong style={{ color: '#38bdf8' }}>Pasto sobre Agua</strong> sin dibujar 47 variantes a mano.
      </p>

      {/* Feature tags */}
      <div
        style={{
          display: 'flex',
          gap: 14,
          flexWrap: 'wrap',
          justifyContent: 'center',
          opacity: badgesProgress,
          transform: `translateY(${interpolate(badgesProgress, [0, 1], [20, 0])}px)`,
        }}
      >
        {[
          { icon: '🌿', label: '1. Pasto sobre Tierra' },
          { icon: '🏖️', label: '2. Tierra sobre Agua' },
          { icon: '🌊', label: '3. Pasto sobre Agua' },
          { icon: '🎮', label: 'Map Tester & Exportación' },
        ].map((item, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 16px',
              borderRadius: 10,
              backgroundColor: 'rgba(15, 23, 42, 0.75)',
              border: '1px solid rgba(145, 205, 255, 0.2)',
              fontSize: 13,
              fontWeight: 600,
              color: '#e2e8f0',
              backdropFilter: 'blur(10px)',
            }}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
