import React from 'react';
import { AbsoluteFill, Audio, staticFile, useCurrentFrame, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const ShowcaseSceneDualGrid: React.FC = () => {
  const frame = useCurrentFrame();

  // Dynamic camera zooms
  let scale = 1.0;
  let originX = 50;
  let originY = 50;

  if (frame >= 30 && frame < 520) {
    // Zoom onto Dual Grid 15 button and 15 tiles grid
    scale = 1.30;
    originX = 42;
    originY = 48;
  } else if (frame >= 520) {
    // Zoom onto sandbox canvas drawing
    scale = 1.34;
    originX = 56;
    originY = 54;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: '#0b0f19' }}>
      <ZoomContainer scale={scale} originX={originX} originY={originY}>
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Tileset Builder · Dual Grid 15">
          <Video
            src={staticFile('clips/clip_showcase_dualgrid.mp4')}
            playbackRate={0.80}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          />
        </BrowserFrame>
      </ZoomContainer>

      {/* Callouts */}
      {frame >= 40 && frame < 580 && (
        <CalloutBadge
          title="Dual Grid 15"
          subtitle="Requiere únicamente 2 tiles base para resolver todas las esquinas"
          badge="Máxima Rapidez"
          accentColor="#ffb86c"
          x={1260}
          y={180}
        />
      )}

      {frame >= 620 && frame < 1200 && (
        <CalloutBadge
          title="TileMapDual Compatible"
          subtitle="Grilla dual desplazada medio bloque: liviana y optimizada para Godot 4"
          badge="Godot 4 Ready"
          accentColor="#ffb86c"
          x={1260}
          y={180}
        />
      )}

      <LowerThird
        title="Tileset Builder · Dual Grid 15 Rápido"
        subtitle="Crea transiciones completas con solo dos tiles base para niveles masivos y eficientes"
        badge="FASE 4: DUAL GRID 15"
        accentColor="#ffb86c"
      />

      <Audio src={staticFile('audio/showcase_scene5.mp3')} />
    </AbsoluteFill>
  );
};
