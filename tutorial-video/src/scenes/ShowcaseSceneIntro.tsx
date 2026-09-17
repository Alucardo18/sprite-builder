import React from 'react';
import { AbsoluteFill, Audio, staticFile, useCurrentFrame } from 'remotion';
import { DualShowcaseIntroCard } from '../components/DualShowcaseIntroCard';

export const ShowcaseSceneIntro: React.FC = () => {
  const frame = useCurrentFrame();

  const pulse = Math.sin(frame / 40) * 0.08 + 1;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#0a0d14',
        justifyContent: 'center',
        alignItems: 'center',
        overflow: 'hidden',
      }}
    >
      {/* Background ambient lighting */}
      <div
        style={{
          position: 'absolute',
          width: 900,
          height: 900,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(87, 223, 188, 0.12) 0%, rgba(10, 13, 20, 0) 70%)',
          top: '20%',
          left: '15%',
          transform: `scale(${pulse}) translate(-50%, -50%)`,
          pointerEvents: 'none',
        }}
      />
      <div
        style={{
          position: 'absolute',
          width: 800,
          height: 800,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(255, 184, 108, 0.08) 0%, rgba(10, 13, 20, 0) 70%)',
          bottom: '10%',
          right: '15%',
          transform: `scale(${1.1 - (pulse - 1)}) translate(50%, 50%)`,
          pointerEvents: 'none',
        }}
      />

      <DualShowcaseIntroCard />

      <Audio src={staticFile('audio/showcase_scene1.mp3')} />
    </AbsoluteFill>
  );
};
