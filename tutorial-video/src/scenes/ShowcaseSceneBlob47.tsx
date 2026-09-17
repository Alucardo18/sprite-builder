import React from 'react';
import { AbsoluteFill, Audio, staticFile, useCurrentFrame, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const ShowcaseSceneBlob47: React.FC = () => {
  const frame = useCurrentFrame();

  // Dynamic camera zooms
  let scale = 1.0;
  let originX = 50;
  let originY = 50;

  if (frame >= 30 && frame < 550) {
    // Zoom onto preset selection and 47 tiles grid
    scale = 1.28;
    originX = 40;
    originY = 48;
  } else if (frame >= 550) {
    // Zoom onto interactive drawing canvas
    scale = 1.34;
    originX = 55;
    originY = 54;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: '#0b0f19' }}>
      <ZoomContainer scale={scale} originX={originX} originY={originY}>
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Tileset Builder · Blob 47">
          <Video
            src={staticFile('clips/clip_showcase_blob47.mp4')}
            playbackRate={0.76}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          />
        </BrowserFrame>
      </ZoomContainer>

      {/* Callouts */}
      {frame >= 40 && frame < 600 && (
        <CalloutBadge
          title="Algoritmo Blob 47"
          subtitle="Genera las 47 combinaciones requeridas para biomas orgánicos"
          badge="47 Losas"
          accentColor="#ffb86c"
          x={1260}
          y={180}
        />
      )}

      {frame >= 640 && frame < 1250 && (
        <CalloutBadge
          title="Autotiling Inteligente"
          subtitle="Pinta en tiempo real: esquinas y bordes se conectan de forma natural"
          badge="Sin Costuras"
          accentColor="#ffb86c"
          x={1260}
          y={180}
        />
      )}

      <LowerThird
        title="Tileset Builder · Algoritmo Blob 47 Orgánico"
        subtitle="De una textura simple a un mapa completo con 47 losas de terreno sin dibujar píxeles a mano"
        badge="FASE 3: TILESET BUILDER"
        accentColor="#ffb86c"
      />

      <Audio src={staticFile('audio/showcase_scene4.mp3')} />
    </AbsoluteFill>
  );
};
