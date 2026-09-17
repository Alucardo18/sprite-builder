import React from 'react';
import { Audio, interpolate, staticFile, useCurrentFrame, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { IntroCard } from '../components/IntroCard';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SceneIntro: React.FC = () => {
  const frame = useCurrentFrame();

  const browserOpacity = interpolate(frame, [180, 230], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const browserScale = interpolate(frame, [180, 230], [0.92, 1], {
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
      <Audio src={staticFile('audio/scene1.mp3')} volume={1} />

      {/* Intro Card Overlay */}
      {frame < 240 && <IntroCard />}

      {/* Browser Viewport */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          padding: '40px 60px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          opacity: browserOpacity,
          transform: `scale(${browserScale})`,
        }}
      >
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="sprite-builder · Ecosistemas Blob 47">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1, x: 0, y: 0 },
              { frame: 450, scale: 1.15, x: -80, y: -40 },
              { frame: 950, scale: 1.25, x: -100, y: -80 },
              { frame: 1480, scale: 1.1, x: -40, y: -30 },
            ]}
          >
            <Video
              src={staticFile('clips/screen_recording.mp4')}
              startFrom={0}
              endAt={1480}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter LowerThird */}
      {frame >= 220 && (
        <LowerThird
          chapter="CAPÍTULO 1 · Introducción"
          title="Ecosistemas de Terreno en 2D con Blob 47"
          subtitle="Aprende a conectar pasto, tierra y agua en un mundo vivo"
          startFrame={220}
          durationInFrames={550}
        />
      )}

      {/* Callout Badge */}
      {frame >= 280 && (
        <CalloutBadge
          step="Concepto Clave"
          title="La Pirámide de Terrenos"
          description="Los mapas naturales se componen de 3 niveles: Agua en la profundidad, Tierra en las orillas y Pasto en la superficie."
          icon="🗺️"
          position="top-right"
          startFrame={280}
          durationInFrames={600}
        />
      )}
    </div>
  );
};
