import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

export const OutroCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({
    frame,
    fps,
    config: { damping: 14, mass: 0.85 },
  });

  const cardsEnter = spring({
    frame: frame - 20,
    fps,
    config: { damping: 15, mass: 1 },
  });

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
        fontFamily: 'Inter, system-ui, sans-serif',
        overflow: 'hidden',
        padding: '0 80px',
      }}
    >
      {/* Background ambient glow */}
      <div
        style={{
          position: 'absolute',
          width: 800,
          height: 800,
          borderRadius: '50%',
          background:
            'radial-gradient(circle, rgba(16, 185, 129, 0.22) 0%, rgba(59, 130, 246, 0.15) 50%, transparent 70%)',
          filter: 'blur(90px)',
        }}
      />

      {/* Headline */}
      <div
        style={{
          textAlign: 'center',
          marginBottom: 36,
          opacity: enter,
          transform: `translateY(${interpolate(enter, [0, 1], [30, 0])}px)`,
        }}
      >
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '5px 16px',
            borderRadius: 999,
            backgroundColor: 'rgba(16, 185, 129, 0.16)',
            border: '1px solid rgba(16, 185, 129, 0.35)',
            marginBottom: 16,
          }}
        >
          <span style={{ fontSize: 13, color: '#34d399', fontWeight: 800 }}>
            LISTO PARA PRODUCCIÓN
          </span>
        </div>
        <h2
          style={{
            fontSize: 54,
            fontWeight: 900,
            margin: 0,
            letterSpacing: '-0.03em',
            background: 'linear-gradient(135deg, #ffffff 40%, #6ee7b7 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          Exporta a tu Motor Favorito
        </h2>
        <p
          style={{
            fontSize: 20,
            color: '#94a3b8',
            marginTop: 12,
            maxWidth: 680,
          }}
        >
          Un solo flujo procedural genera atlas completos y configuraciones listas para pintar en cualquier motor.
        </p>
      </div>

      {/* Export Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 22,
          width: '100%',
          maxWidth: 960,
          marginBottom: 40,
          opacity: cardsEnter,
          transform: `translateY(${interpolate(cardsEnter, [0, 1], [30, 0])}px)`,
        }}
      >
        {[
          {
            icon: '🎮',
            title: 'Godot 4 Bundle',
            desc: 'terrain_tiles.png + install_terrain_tileset.gd y metadatos TileMapDual automáticos.',
            tag: 'Godot 4.x (.zip)',
            color: '#478cbf',
          },
          {
            icon: '⚡',
            title: 'Unity RuleTile',
            desc: 'Atlas PNG + CreateRuleTile.cs editor script y RuleTileConfig.json preconfigurado.',
            tag: 'Unity 2D Tilemap',
            color: '#818cf8',
          },
          {
            icon: '🗺️',
            title: 'Tiled TSX',
            desc: 'Atlas + archivo .tsx con WangSet de 4 esquinas configurado para brocha de terreno.',
            tag: 'Tiled Editor (.tsx)',
            color: '#34d399',
          },
        ].map((engine, idx) => (
          <div
            key={idx}
            style={{
              padding: '24px 20px',
              borderRadius: 16,
              backgroundColor: 'rgba(15, 23, 42, 0.85)',
              border: `1px solid rgba(255, 255, 255, 0.12)`,
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
              backdropFilter: 'blur(12px)',
              boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 28 }}>{engine.icon}</span>
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  padding: '3px 8px',
                  borderRadius: 6,
                  backgroundColor: 'rgba(255, 255, 255, 0.08)',
                  color: engine.color,
                }}
              >
                {engine.tag}
              </span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#f8fafc' }}>
              {engine.title}
            </div>
            <div style={{ fontSize: 12, lineHeight: 1.5, color: '#94a3b8' }}>
              {engine.desc}
            </div>
          </div>
        ))}
      </div>

      {/* CTA Footer */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          opacity: cardsEnter,
        }}
      >
        <div
          style={{
            padding: '12px 28px',
            borderRadius: 12,
            background: 'linear-gradient(135deg, #10b981, #059669)',
            color: '#ffffff',
            fontWeight: 800,
            fontSize: 15,
            boxShadow: '0 8px 25px rgba(16, 185, 129, 0.4)',
          }}
        >
          uv run sprite-builder ui
        </div>
        <span style={{ fontSize: 14, color: '#64748b' }}>
          Documentación completa en docs/tileset_pipeline.md
        </span>
      </div>
    </div>
  );
};
