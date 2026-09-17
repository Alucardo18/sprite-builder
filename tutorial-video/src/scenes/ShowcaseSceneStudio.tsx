import React from 'react';
import { AbsoluteFill, Audio, staticFile, useCurrentFrame, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const ShowcaseSceneStudio: React.FC = () => {
  const frame = useCurrentFrame();

  // Dynamic camera zooms on the animated canvas and timeline
  let scale = 1.0;
  let originX = 50;
  let originY = 50;

  if (frame >= 30 && frame < 650) {
    // Zoom onto the animated character canvas and play controls
    scale = 1.34;
    originX = 50;
    originY = 66;
  } else if (frame >= 650) {
    // Zoom onto the onion skin and pixel layers
    scale = 1.28;
    originX = 45;
    originY = 62;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: '#0b0f19' }}>
      <ZoomContainer scale={scale} originX={originX} originY={originY}>
        <BrowserFrame url="http://localhost:8501/?page=sprites" title="Sprite Builder · Estudio de Animación">
          <Video
            src={staticFile('clips/clip_showcase_studio_anim.mp4')}
            startFrom={100}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          />
        </BrowserFrame>
      </ZoomContainer>

      {/* Callouts */}
      {frame >= 40 && frame < 620 && (
        <CalloutBadge
          title="Reproductor en Vivo (GIF Loop)"
          subtitle="Previsualiza el personaje animándose en tiempo real a 8 FPS"
          badge="Animación Activa"
          accentColor="#57dfbc"
          x={1260}
          y={180}
        />
      )}

      {frame >= 650 && frame < 1200 && (
        <CalloutBadge
          title="Onion Skin Multicapa"
          subtitle="Capas transparentes (rojo y azul) para calibrar el movimiento"
          badge="Guía Visual"
          accentColor="#57dfbc"
          x={1260}
          y={180}
        />
      )}

      <LowerThird
        title="Estudio de Capas · Reproducción en Bucle"
        subtitle="Observa la animación en tiempo real tipo GIF, ajusta FPS y retoca detalles con Onion Skin"
        badge="FASE 2: ESTUDIO & ANIMACIÓN"
        accentColor="#57dfbc"
      />

      <Audio src={staticFile('audio/showcase_scene3.mp3')} />
    </AbsoluteFill>
  );
};
