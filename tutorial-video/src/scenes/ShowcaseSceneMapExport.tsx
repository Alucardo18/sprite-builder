import React from 'react';
import { AbsoluteFill, Audio, staticFile, useCurrentFrame, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const ShowcaseSceneMapExport: React.FC = () => {
  const frame = useCurrentFrame();

  // Dynamic camera zooms
  let scale = 1.0;
  let originX = 50;
  let originY = 50;

  if (frame >= 30 && frame < 520) {
    // Zoom onto procedural map canvas
    scale = 1.25;
    originX = 50;
    originY = 46;
  } else if (frame >= 520) {
    // Zoom onto export buttons
    scale = 1.30;
    originX = 50;
    originY = 62;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: '#0b0f19' }}>
      <ZoomContainer scale={scale} originX={originX} originY={originY}>
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Tileset Builder · Map Tester & Export">
          <Video
            src={staticFile('clips/clip_showcase_maptester.mp4')}
            playbackRate={0.90}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          />
        </BrowserFrame>
      </ZoomContainer>

      {/* Callouts */}
      {frame >= 40 && frame < 550 && (
        <CalloutBadge
          title="Map Tester Interactivo"
          subtitle="Generación procedural y prueba de autotiling en tiempo real"
          badge="Prueba en Vivo"
          accentColor="#57dfbc"
          x={1260}
          y={180}
        />
      )}

      {frame >= 590 && frame < 1120 && (
        <CalloutBadge
          title="Exportación a Motores"
          subtitle="TileSet (.tres) para Godot 4 y RuleTile para Unity con metadatos listos"
          badge="1-Clic"
          accentColor="#57dfbc"
          x={1260}
          y={180}
        />
      )}

      <LowerThird
        title="Map Tester y Exportación Lista para Motores"
        subtitle="Verifica la interacción en mapas reales y descarga el paquete listo para Godot 4 o Unity"
        badge="FASE 5: TEST & EXPORT"
        accentColor="#57dfbc"
      />

      <Audio src={staticFile('audio/showcase_scene6.mp3')} />
    </AbsoluteFill>
  );
};
