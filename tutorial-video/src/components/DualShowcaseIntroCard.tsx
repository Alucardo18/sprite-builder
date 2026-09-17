import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

export const DualShowcaseIntroCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 90 },
  });

  const subtitleOpacity = interpolate(frame, [25, 50], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const cardsProgress = spring({
    frame: Math.max(0, frame - 45),
    fps,
    config: { damping: 15, stiffness: 85 },
  });

  const floatY = Math.sin(frame / 35) * 5;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        transform: `translateY(${floatY}px)`,
        maxWidth: 1300,
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
          padding: '8px 26px',
          color: '#57dfbc',
          fontSize: 16,
          fontWeight: 700,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          marginBottom: 20,
          opacity: Math.min(1, frame / 20),
        }}
      >
        <span>⚡</span>
        <span>Suite Integrada de Desarrollo 2D · Producción Rápida</span>
      </div>

      {/* Main Title */}
      <h1
        style={{
          fontSize: 78,
          fontWeight: 900,
          color: '#ffffff',
          lineHeight: 1.05,
          letterSpacing: '-0.03em',
          margin: 0,
          transform: `scale(${interpolate(titleProgress, [0, 1], [0.85, 1])})`,
          opacity: titleProgress,
          background: 'linear-gradient(135deg, #ffffff 30%, #57dfbc 75%, #ffb86c 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
        }}
      >
        Sprite Builder & Tileset Studio
      </h1>

      {/* Subtitle */}
      <p
        style={{
          fontSize: 26,
          color: '#b5c0d0',
          maxWidth: 960,
          marginTop: 18,
          marginBottom: 42,
          lineHeight: 1.45,
          opacity: subtitleOpacity,
        }}
      >
        El flujo completo para videojuegos 2D: limpia y anima personajes en bucle con <strong style={{ color: '#57dfbc' }}>Sheet Studio</strong>, y crea terrenos orgánicos con <strong style={{ color: '#ffb86c' }}>Blob 47 y Dual Grid 15</strong>.
      </p>

      {/* Two Pillars Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 32,
          width: '100%',
          maxWidth: 1080,
          opacity: cardsProgress,
          transform: `translateY(${interpolate(cardsProgress, [0, 1], [30, 0])}px)`,
        }}
      >
        {/* Card 1: Sprite Builder */}
        <div
          style={{
            backgroundColor: 'rgba(18, 24, 38, 0.75)',
            border: '1px solid rgba(87, 223, 188, 0.35)',
            borderRadius: 20,
            padding: '28px 32px',
            textAlign: 'left',
            boxShadow: '0 12px 35px rgba(0, 0, 0, 0.45)',
            backdropFilter: 'blur(16px)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
            <span style={{ fontSize: 32 }}>⚔️</span>
            <div>
              <h3 style={{ margin: 0, color: '#ffffff', fontSize: 24, fontWeight: 800 }}>Sheet Studio</h3>
              <span style={{ color: '#57dfbc', fontSize: 13, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Personajes & Animación</span>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#d0dae8', fontSize: 15 }}>
              <span style={{ color: '#57dfbc' }}>✓</span> Fondo limpio & eliminación de halo
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#d0dae8', fontSize: 15 }}>
              <span style={{ color: '#57dfbc' }}>✓</span> Alineación por centro de gravedad (torso)
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#d0dae8', fontSize: 15 }}>
              <span style={{ color: '#57dfbc' }}>✓</span> Estudio interactivo con preview animado tipo GIF
            </div>
          </div>
        </div>

        {/* Card 2: Tileset Builder */}
        <div
          style={{
            backgroundColor: 'rgba(18, 24, 38, 0.75)',
            border: '1px solid rgba(255, 184, 108, 0.35)',
            borderRadius: 20,
            padding: '28px 32px',
            textAlign: 'left',
            boxShadow: '0 12px 35px rgba(0, 0, 0, 0.45)',
            backdropFilter: 'blur(16px)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
            <span style={{ fontSize: 32 }}>🌿</span>
            <div>
              <h3 style={{ margin: 0, color: '#ffffff', fontSize: 24, fontWeight: 800 }}>Tileset Builder</h3>
              <span style={{ color: '#ffb86c', fontSize: 13, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Terrenos & Autotiling</span>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#d0dae8', fontSize: 15 }}>
              <span style={{ color: '#ffb86c' }}>✓</span> Blob 47: 47 losas orgánicas sin costuras
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#ffb86c' }}>
              <span style={{ color: '#ffb86c' }}>✓</span> Dual Grid 15: Autotiling ultra rápido con 2 tiles
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#d0dae8', fontSize: 15 }}>
              <span style={{ color: '#ffb86c' }}>✓</span> Map Tester en vivo y exportación a Godot 4
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
