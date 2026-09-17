import React from 'react';
import { Audio, staticFile, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SceneMapTester: React.FC = () => {
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
      {/* Spanish Voiceover */}
      <Audio src={staticFile('audio/scene4.mp3')} volume={1} />

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
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Map Tester · Pintado Interactivo">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.05, x: 0, y: 0 },
              { frame: 180, scale: 1.36, x: -120, y: -100 }, // Focus on preset controls
              { frame: 450, scale: 1.42, x: 0, y: -140 },    // Focus on regenerated map
              { frame: 720, scale: 1.38, x: -80, y: -160 },  // Inverting & applying brush
              { frame: 1020, scale: 1.15, x: 0, y: -40 },
            ]}
          >
            <Video
              src={staticFile('clips/screen_recording.mp4')}
              startFrom={3540}
              endAt={4560}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter LowerThird */}
      <LowerThird
        chapter="CAPÍTULO 4 · Map Tester"
        title="Validación en Lienzo de Mapa Jugable"
        subtitle="Generación procedural y pintado en tiempo real sin atlas externo"
        startFrame={30}
        durationInFrames={380}
      />

      {/* Callout Badges */}
      <CalloutBadge
        step="Generador Procedural"
        title="Generación de Islas y Cuevas"
        description="Genera mapas con un solo clic. El motor resuelve al instante las 47 combinaciones de esquinas y bordes."
        icon="🎲"
        position="top-right"
        startFrame={40}
        durationInFrames={460}
      />

      <CalloutBadge
        step="Pincel Interactivo"
        title="Pintado y Transiciones Dinámicas"
        description="Pinta en cualquier celda para comprobar la reactividad del autotile en tiempo real, sin cargar imágenes externas."
        icon="🖌️"
        position="top-right"
        startFrame={520}
        durationInFrames={480}
      />
    </div>
  );
};
