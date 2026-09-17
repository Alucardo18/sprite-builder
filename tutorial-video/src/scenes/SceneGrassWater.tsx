import React from 'react';
import { Audio, staticFile, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SceneGrassWater: React.FC = () => {
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
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Pattern Studio · Pasto sobre Agua">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.05, x: 0, y: 0 },
              { frame: 180, scale: 1.35, x: -70, y: -70 }, // Focus on 'Pasto sobre agua' button
              { frame: 480, scale: 1.45, x: -140, y: -110 }, // Focus on cliff tiles
              { frame: 850, scale: 1.38, x: 140, y: -100 },  // Focus on sandbox floating island
              { frame: 1340, scale: 1.15, x: 40, y: -40 },
            ]}
          >
            <Video
              src={staticFile('clips/clip4_grass_water.mp4')}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter Title */}
      <LowerThird
        chapter="CAPÍTULO 4 · Patrón 3"
        title="Pasto sobre Agua (Grass over Water)"
        subtitle="Acantilados directos, islas flotantes y riberas sin tierra expuesta"
        startFrame={30}
        durationInFrames={420}
      />

      {/* Callout Badges */}
      <CalloutBadge
        step="Patrón 3"
        title="Acantilados al Mar"
        description="Conecta el pasto verde directo con el agua profunda sin tierra intermedia. El contraste de color crea una caída visual empinada."
        icon="🌊"
        position="top-right"
        startFrame={40}
        durationInFrames={480}
      />

      <CalloutBadge
        step="Islas Flotantes"
        title="Bordes de Alta Definición"
        description="Perfecto para archipiélagos mágicos o ríos caudalosos donde la vegetación crece hasta el mismo borde del agua."
        icon="🏝️"
        position="top-right"
        startFrame={540}
        durationInFrames={500}
      />
    </div>
  );
};
