import React from 'react';
import { Audio, staticFile, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SceneWizard: React.FC = () => {
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
      <Audio src={staticFile('audio/scene2.mp3')} volume={1} />

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
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Wizard · Blob 47 & Dual Grid 15">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.05, x: 0, y: 0 },
              { frame: 200, scale: 1.35, x: -120, y: -90 },  // Focus on Blob 47 & Dual Grid radio options
              { frame: 700, scale: 1.45, x: -160, y: -120 }, // Focus on HEX inputs #2d7a3a & #4a9e5c
              { frame: 1050, scale: 1.35, x: -120, y: -180 }, // Focus on 'Crear y Activar' button
              { frame: 1440, scale: 1.15, x: -40, y: -50 },
            ]}
          >
            <Video
              src={staticFile('clips/screen_recording.mp4')}
              startFrom={900}
              endAt={2340}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter Title */}
      <LowerThird
        chapter="CAPÍTULO 2 · Asistente Rápido"
        title="Blob 47 & Dual Grid con Sincronización HEX"
        subtitle="Reglas autotile configurables con paleta de dos materiales en tiempo real"
        startFrame={30}
        durationInFrames={420}
      />

      {/* Step Badges */}
      <CalloutBadge
        step="Reglas Autotile"
        title="Blob 47 y Dual Grid 15"
        description="Selecciona Blob 47 para terrenos orgánicos de 8 vecinos con todas las esquinas y uniones, o Dual Grid 15 para prototipado rápido."
        icon="⚡"
        position="top-right"
        startFrame={40}
        durationInFrames={460}
      />

      <CalloutBadge
        step="Paleta Sincronizada"
        title="Control HEX Bidireccional"
        description="Interactúa con la rueda de color o ingresa directamente #2d7a3a y #4a9e5c con refresco instantáneo de swatch y preview."
        icon="🎨"
        position="top-right"
        startFrame={520}
        durationInFrames={480}
      />

      <CalloutBadge
        step="Activación 1-Clic"
        title="Generación Procedural Inmediata"
        description="Al pulsar 'Crear y Activar', se generan los starter tiles y el set queda listo para inspeccionarse y pintarse."
        icon="✨"
        position="top-right"
        startFrame={1020}
        durationInFrames={380}
      />
    </div>
  );
};
