import React from 'react';
import { Audio, staticFile, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SpriteScenePrepare: React.FC = () => {
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
      <Audio src={staticFile('audio/sprite_scene3.mp3')} volume={1} />

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
        <BrowserFrame url="http://localhost:8501/?page=sprites" title="Sheet Studio · Preparar Poses y Segmentación">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.05, x: 0, y: 0 },
              { frame: 180, scale: 1.2, x: 0, y: -40 },
              { frame: 480, scale: 1.25, x: -20, y: -60 },
              { frame: 850, scale: 1.3, x: -30, y: -70 },
              { frame: 1360, scale: 1.05, x: 0, y: 0 },
            ]}
          >
            <Video
              src={staticFile('clips/clip_sprite3_prepare.mp4')}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter Title */}
      <LowerThird
        chapter="CAPÍTULO 3 · SEGMENTACIÓN"
        title="Preparar Poses y Grilla Inicial"
        subtitle="Delimitación provisional de las 16 fases del ciclo de animación"
        startFrame={30}
        durationInFrames={440}
      />

      {/* Callout Badges */}
      <CalloutBadge
        step="Paso 2"
        title="Detección Previa, No Corte Final"
        description="Asigna cada pose a su región aproximada. La hoja se mantiene íntegra mientras preparas la alineación."
        startFrame={180}
        durationInFrames={500}
        top={90}
        right={90}
      />

      <CalloutBadge
        step="16 Frames"
        title="Matriz 4 × 4 Uniforme"
        description="Cada cuadro del guerrero jaguar queda identificado para que el motor de físicas y animación lea la secuencia exacta."
        startFrame={720}
        durationInFrames={500}
        top={90}
        right={90}
      />
    </div>
  );
};
