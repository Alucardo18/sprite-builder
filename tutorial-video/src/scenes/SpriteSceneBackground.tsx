import React from 'react';
import { Audio, staticFile, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SpriteSceneBackground: React.FC = () => {
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
      <Audio src={staticFile('audio/sprite_scene2.mp3')} volume={1} />

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
        <BrowserFrame url="http://localhost:8501/?page=sprites" title="Sheet Studio · Remoción de Fondo y Limpieza">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.05, x: 0, y: 0 },
              { frame: 180, scale: 1.25, x: -120, y: -40 }, // Focus on sidebar background removal controls
              { frame: 540, scale: 1.28, x: -130, y: -60 }, // Focus on tolerance & fringe sliders
              { frame: 850, scale: 1.22, x: 40, y: -40 },   // Focus on main canvas showing transparent sprite
              { frame: 1520, scale: 1.05, x: 0, y: 0 },
            ]}
          >
            <Video
              src={staticFile('clips/clip_sprite2_background.mp4')}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter Title */}
      <LowerThird
        chapter="CAPÍTULO 2 · LIMPIEZA"
        title="Remoción de Fondo No Destructiva"
        subtitle="Tolerancia RGB, fringe cleanup y preservación de contornos oscuros"
        startFrame={30}
        durationInFrames={450}
      />

      {/* Callout Badges */}
      <CalloutBadge
        step="Paso 1"
        title="Eliminación de Halos (Fringe)"
        description="El limpiador de fringe desvanece halos blancos y bordes sucios sin erosionar los píxeles originales de tu personaje."
        startFrame={220}
        durationInFrames={550}
        top={90}
        right={90}
      />

      <CalloutBadge
        step="No Destructivo"
        title="Conserva la Paleta Pura"
        description="Sprite Builder respeta la integridad cromática. Las modificaciones se calculan sobre capas reversibles sin resampling."
        startFrame={800}
        durationInFrames={550}
        top={90}
        right={90}
      />
    </div>
  );
};
