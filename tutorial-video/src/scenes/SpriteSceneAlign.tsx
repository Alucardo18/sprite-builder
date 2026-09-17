import React from 'react';
import { Audio, staticFile, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { CalloutBadge } from '../components/CalloutBadge';
import { LowerThird } from '../components/LowerThird';
import { ZoomContainer } from '../components/ZoomContainer';

export const SpriteSceneAlign: React.FC = () => {
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
      <Audio src={staticFile('audio/sprite_scene4.mp3')} volume={1} />

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
        <BrowserFrame url="http://localhost:8501/?page=sprites" title="Sheet Studio · Alineación Multi-Anchor">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.05, x: 0, y: 0 },
              { frame: 180, scale: 1.25, x: -120, y: -40 }, // Focus on sidebar profile (Walk/Idle)
              { frame: 480, scale: 1.25, x: -30, y: -70 },  // Focus on 'Autoalinear todo' button
              { frame: 800, scale: 1.25, x: 0, y: -80 },    // Focus on multi-anchor crosshairs
              { frame: 1620, scale: 1.05, x: 0, y: 0 },
            ]}
          >
            <Video
              src={staticFile('clips/clip_sprite4_align.mp4')}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter Title */}
      <LowerThird
        chapter="CAPÍTULO 4 · ESTABILIDAD"
        title="Alineación Multi-Anchor Inteligente"
        subtitle="Centro de gravedad en torso y pelvis para eliminar vibraciones en armas y saltos"
        startFrame={30}
        durationInFrames={460}
      />

      {/* Callout Badges */}
      <CalloutBadge
        step="Paso 3"
        title="Torso & Pelvis como Ancla"
        description="Alinear por la caja envolvente total hace 'bailar' al personaje al alzar un arma. El ancla de torso fija el centro de masa."
        startFrame={180}
        durationInFrames={550}
        top={90}
        right={90}
      />

      <CalloutBadge
        step="1-Click"
        title="Autoalinear Todo (X/Y Entero)"
        description="Fija todas las poses instantáneamente. La corrección geométrica utiliza traslación pura de píxeles enteros sin distorsión."
        startFrame={780}
        durationInFrames={580}
        top={90}
        right={90}
      />
    </div>
  );
};
