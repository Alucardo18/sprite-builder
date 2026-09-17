import React from 'react';
import { Audio, staticFile } from 'remotion';
import { SpriteIntroCard } from '../components/SpriteIntroCard';

export const SpriteSceneIntro: React.FC = () => {
  return (
    <div
      style={{
        position: 'relative',
        width: 1920,
        height: 1080,
        backgroundColor: '#070b14',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {/* Latin American Spanish Voiceover (Jorge - México) */}
      <Audio src={staticFile('audio/sprite_scene1.mp3')} volume={1} />

      {/* Modern Background Grid glow */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            radial-gradient(circle at 50% 40%, rgba(87, 223, 188, 0.12) 0%, transparent 60%),
            radial-gradient(circle at 80% 80%, rgba(255, 104, 152, 0.08) 0%, transparent 50%),
            linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px)
          `,
          backgroundSize: '100% 100%, 100% 100%, 48px 48px, 48px 48px',
          pointerEvents: 'none',
        }}
      />

      <SpriteIntroCard />
    </div>
  );
};
