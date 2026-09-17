import React from 'react';
import { Audio, staticFile, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SceneStudio: React.FC = () => {
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
      <Audio src={staticFile('audio/scene3.mp3')} volume={1} />

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
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Pattern Studio · Blob 47 & Sandbox">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.08, x: 0, y: 0 },
              { frame: 180, scale: 1.34, x: -120, y: -70 }, // Focus on Blob 47 preset buttons
              { frame: 480, scale: 1.4, x: -150, y: -110 }, // Focus on 47 autotiles matrix
              { frame: 820, scale: 1.38, x: 140, y: -100 },  // Focus on sandbox connected map
              { frame: 1200, scale: 1.15, x: 0, y: -40 },
            ]}
          >
            <Video
              src={staticFile('clips/screen_recording.mp4')}
              startFrom={2340}
              endAt={3540}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter LowerThird */}
      <LowerThird
        chapter="CAPÍTULO 3 · Pattern Studio"
        title="Blob 47: 47 Autotiles y Sandbox Conectado"
        subtitle="8 vecinos, esquinas biseladas/redondeadas y sombras en tiempo real"
        startFrame={30}
        durationInFrames={400}
      />

      {/* Callout Badges */}
      <CalloutBadge
        step="Blob 47"
        title="47 Formas Orgánicas Completas"
        description="El sistema Blob 47 genera las 47 combinaciones de 8 vecinos para bordes, esquinas interiores y exteriores sin costuras."
        icon="🌿"
        position="top-right"
        startFrame={40}
        durationInFrames={520}
      />

      <CalloutBadge
        step="Estudio y Sandbox"
        title="Presets 1-Clic y Validación"
        description="Aplica biomas automáticos como 'Pasto sobre tierra' y prueba el autotile interactuando con el mapa insular del sandbox."
        icon="🏝️"
        position="top-right"
        startFrame={580}
        durationInFrames={560}
      />
    </div>
  );
};
