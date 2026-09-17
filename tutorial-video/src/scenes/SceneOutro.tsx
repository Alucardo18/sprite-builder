import React from 'react';
import { Audio, interpolate, staticFile, useCurrentFrame, Video } from 'remotion';
import { BrowserFrame } from '../components/BrowserFrame';
import { LowerThird } from '../components/LowerThird';
import { OutroCard } from '../components/OutroCard';
import { ZoomContainer } from '../components/ZoomContainer';

export const SceneOutro: React.FC = () => {
  const frame = useCurrentFrame();

  const outroCardOpacity = interpolate(frame, [420, 480], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

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
      <Audio src={staticFile('audio/scene5.mp3')} volume={1} />

      {/* Browser with Export Options */}
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
        <BrowserFrame url="http://localhost:8501/?page=tilesets" title="Exportación · Godot 4 / Unity / Tiled">
          <ZoomContainer
            keyframes={[
              { frame: 0, scale: 1.15, x: 0, y: -100 },
              { frame: 180, scale: 1.35, x: 0, y: -180 }, // Focus on Godot, Unity, Tiled export buttons
              { frame: 420, scale: 1.4, x: -60, y: -200 },
            ]}
          >
            <Video
              src={staticFile('clips/screen_recording.mp4')}
              startFrom={4560}
              endAt={5580}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            />
          </ZoomContainer>
        </BrowserFrame>
      </div>

      {/* Chapter LowerThird during video */}
      {frame < 440 && (
        <LowerThird
          chapter="CAPÍTULO 5 · Exportación"
          title="Bundles Listos para Godot 4, Unity y Tiled"
          subtitle="Exporta tanto Blob 47 como Dual Grid con scripts e instaladores incluidos"
          startFrame={20}
          durationInFrames={400}
        />
      )}

      {/* Outro Card Overlay */}
      {frame >= 420 && (
        <div style={{ position: 'absolute', inset: 0, opacity: outroCardOpacity }}>
          <OutroCard />
        </div>
      )}
    </div>
  );
};
