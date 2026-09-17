import React from 'react';
import { Audio, interpolate, staticFile, useCurrentFrame, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { OutroCard } from '../components/OutroCard';
import { ZoomContainer } from '../components/ZoomContainer';

export const SceneEcosystemOutro: React.FC = () => {
  const frame = useCurrentFrame();

  const outroCardOpacity = interpolate(frame, [650, 720], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div
      style={{
        position: 'relative',
        width: 1920,
        height: 1080,
        backgroundColor: '#070b14',
        overflow: 'hidden',
      }}
    >
      {/* Spanish Voiceover (Jorge - México) */}
      <Audio src={staticFile('audio/scene5.mp3')} volume={1} />

      {/* Browser with Map Tester & Export Options */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          padding: '40px 60px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Map Tester & Exportación · Ecosistema Completo">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.05, x: 0, y: 0 },
              { frame: 180, scale: 1.35, x: -100, y: -100 }, // Focus on Map Tester preset controls
              { frame: 450, scale: 1.4, x: 0, y: -140 },    // Focus on painted map
              { frame: 650, scale: 1.25, x: -40, y: -180 }, // Focus on export buttons
              { frame: 1560, scale: 1.1, x: 0, y: -50 },
            ]}
          >
            <Video
              src={staticFile('clips/clip5_map_export.mp4')}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter LowerThird */}
      {frame < 660 && (
        <LowerThird
          chapter="CAPÍTULO 5 · El Ecosistema Completo"
          title="Validación en Mapa Jugable & Exportación"
          subtitle="Combina las 3 capas en Map Tester y exporta para Godot, Unity o Tiled"
          startFrame={20}
          durationInFrames={460}
        />
      )}

      {/* Callout Badge */}
      {frame < 660 && (
        <CalloutBadge
          step="Ecosistema 2D"
          title="Mundo Vivo y Conectado"
          description="Al juntar los 3 patrones tienes un mar con islas de tierra y praderas verdes sin costuras rotas."
          icon="🎮"
          position="top-right"
          startFrame={40}
          durationInFrames={500}
        />
      )}

      {/* Outro Card Overlay */}
      {frame >= 650 && (
        <div style={{ position: 'absolute', inset: 0, opacity: outroCardOpacity }}>
          <OutroCard />
        </div>
      )}
    </div>
  );
};
