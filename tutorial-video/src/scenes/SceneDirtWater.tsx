import React from 'react';
import { Audio, staticFile, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SceneDirtWater: React.FC = () => {
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
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Pattern Studio · Tierra sobre Agua">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.05, x: 0, y: 0 },
              { frame: 180, scale: 1.35, x: -100, y: -70 }, // Focus on 'Tierra sobre agua' button
              { frame: 520, scale: 1.45, x: -150, y: -110 }, // Focus on coast tiles
              { frame: 900, scale: 1.38, x: 140, y: -100 },  // Focus on sandbox island
              { frame: 1420, scale: 1.15, x: 40, y: -40 },
            ]}
          >
            <Video
              src={staticFile('clips/clip3_dirt_water.mp4')}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter Title */}
      <LowerThird
        chapter="CAPÍTULO 3 · Patrón 2"
        title="Tierra sobre Agua (Dirt over Water)"
        subtitle="Costas, playas y riberas con volumen y sombras proyectadas"
        startFrame={30}
        durationInFrames={440}
      />

      {/* Callout Badges */}
      <CalloutBadge
        step="Patrón 2"
        title="Costas y Volumen Vertical"
        description="Representa el suelo firme elevado sobre el nivel del agua. Añade automáticamente una sombra sutil que da profundidad al mar."
        icon="🏖️"
        position="top-right"
        startFrame={40}
        durationInFrames={520}
      />

      <CalloutBadge
        step="Efecto de Ribera"
        title="Biselado de Costa Automático"
        description="En el sandbox observamos cómo la tierra se rodea de agua de forma limpia, simulando islas y penínsulas navegables."
        icon="🌊"
        position="top-right"
        startFrame={580}
        durationInFrames={540}
      />
    </div>
  );
};
