import React from 'react';
import { Audio, staticFile, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SceneGrassDirt: React.FC = () => {
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
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Pattern Studio · Pasto sobre Tierra">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.05, x: 0, y: 0 },
              { frame: 180, scale: 1.35, x: -140, y: -70 }, // Focus on 'Pasto sobre tierra' button
              { frame: 550, scale: 1.45, x: -160, y: -110 }, // Focus on the 47 autotiles canvas
              { frame: 950, scale: 1.38, x: 140, y: -100 },  // Focus on sandbox drawing grass patch
              { frame: 1540, scale: 1.15, x: 40, y: -40 },
            ]}
          >
            <Video
              src={staticFile('clips/clip2_grass_dirt.mp4')}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter Title */}
      <LowerThird
        chapter="CAPÍTULO 2 · Patrón 1"
        title="Pasto sobre Tierra (Grass over Dirt)"
        subtitle="La base de cualquier pradera: césped superior sobre suelo firme"
        startFrame={30}
        durationInFrames={450}
      />

      {/* Callout Badges */}
      <CalloutBadge
        step="Patrón 1"
        title="Base de Pradera Natural"
        description="El césped forma la capa superior. Los mechones verdes caen suavemente sobre la tierra marrón eliminando la cuadrícula rígida."
        icon="🌿"
        position="top-right"
        startFrame={40}
        durationInFrames={540}
      />

      <CalloutBadge
        step="47 Autotiles"
        title="Uniones Orgánicas sin Costuras"
        description="Las 47 piezas resuelven esquinas interiores y exteriores, senderos angostos y claros de bosque automáticamente."
        icon="🧩"
        position="top-right"
        startFrame={620}
        durationInFrames={580}
      />
    </div>
  );
};
