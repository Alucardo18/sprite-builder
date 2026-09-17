import React from 'react';
import { Audio, staticFile, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SpriteSceneExport: React.FC = () => {
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
      <Audio src={staticFile('audio/sprite_scene5.mp3')} volume={1} />

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
        <BrowserFrame url="http://localhost:8501/?page=sprites" title="Sheet Studio · Cortes Finales y Exportación">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.05, x: 0, y: 0 },
              { frame: 180, scale: 1.2, x: -20, y: -40 },  // Focus on Tab 4 Cortes finales
              { frame: 450, scale: 1.25, x: 0, y: -50 },   // Focus on Tab 5 Export
              { frame: 750, scale: 1.25, x: -30, y: -70 }, // Focus on 'Exportar hoja nativa completa'
              { frame: 1100, scale: 1.2, x: 20, y: -60 },  // Focus on frames individuales
              { frame: 1540, scale: 1.05, x: 0, y: 0 },
            ]}
          >
            <Video
              src={staticFile('clips/clip_sprite5_export.mp4')}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter Title */}
      <LowerThird
        chapter="CAPÍTULO 5 · EXPORTACIÓN"
        title="Cortes Finales y Paquetes de Motor"
        subtitle="Hoja nativa con AtlasTexture para Godot 4 y cuadros PNG individuales"
        startFrame={30}
        durationInFrames={460}
      />

      {/* Callout Badges */}
      <CalloutBadge
        step="Paso 4 & 5"
        title="Celda Canónica Uniforme"
        description="Todas las celdas comparten dimensiones exactas para que la importación en Godot o Unity sea instantánea y sin descalces."
        startFrame={180}
        durationInFrames={500}
        top={90}
        right={90}
      />

      <CalloutBadge
        step="Godot & Unity"
        title="AtlasTexture + Frames PNG"
        description="Descarga tu hoja nativa con atlas o extrae cada cuadro independiente manteniendo intacta la nitidez del pixel art."
        startFrame={720}
        durationInFrames={550}
        top={90}
        right={90}
      />
    </div>
  );
};
