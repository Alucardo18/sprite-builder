import React from 'react';
import { AbsoluteFill, Audio, staticFile, useCurrentFrame, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const ShowcaseSceneSprites: React.FC = () => {
  const frame = useCurrentFrame();

  // Dynamic camera zooms
  let scale = 1.0;
  let originX = 50;
  let originY = 50;

  if (frame >= 40 && frame < 460) {
    // Zoom onto Background removal controls
    scale = 1.28;
    originX = 35;
    originY = 45;
  } else if (frame >= 460 && frame < 1050) {
    // Zoom onto Alignment controls and auto-align button
    scale = 1.32;
    originX = 58;
    originY = 52;
  } else if (frame >= 1050) {
    // Zoom onto Final Cuts grid
    scale = 1.22;
    originX = 50;
    originY = 55;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: '#0b0f19' }}>
      <ZoomContainer scale={scale} originX={originX} originY={originY}>
        <BrowserFrame url="http://localhost:8501/?page=sprites" title="Sprite Builder · Sheet Studio">
          <Video
            src={staticFile('clips/clip_showcase_sprites.mp4')}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          />
        </BrowserFrame>
      </ZoomContainer>

      {/* Callouts */}
      {frame >= 40 && frame < 450 && (
        <CalloutBadge
          title="Fondo Limpio y No Destructivo"
          subtitle="Tolerancia precisa + eliminación de halo preservando contornos"
          badge="1. Fondo"
          accentColor="#57dfbc"
          x={1260}
          y={180}
        />
      )}

      {frame >= 480 && frame < 1020 && (
        <CalloutBadge
          title="Alineación Inteligente"
          subtitle="Anclaje por torso y pelvis: centro de gravedad sin temblores"
          badge="2. Alineación"
          accentColor="#57dfbc"
          x={1260}
          y={180}
        />
      )}

      {frame >= 1050 && frame < 1480 && (
        <CalloutBadge
          title="Cortes Uniformes"
          subtitle="Dimensiones consistentes sin recortar armas ni accesorios"
          badge="3. Cortes Finales"
          accentColor="#57dfbc"
          x={1260}
          y={180}
        />
      )}

      <LowerThird
        title="Sheet Studio · Remoción de Fondo y Alineación"
        subtitle="Limpia fondos, ancla por centro de gravedad y corta poses sin alterar el arte original"
        badge="FASE 1: SPRITE BUILDER"
        accentColor="#57dfbc"
      />

      <Audio src={staticFile('audio/showcase_scene2.mp3')} />
    </AbsoluteFill>
  );
};
