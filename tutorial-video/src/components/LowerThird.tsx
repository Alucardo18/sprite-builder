import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

interface LowerThirdProps {
  chapter: string;
  title: string;
  subtitle?: string;
  startFrame?: number;
  durationInFrames?: number;
}

export const LowerThird: React.FC<LowerThirdProps> = ({
  chapter,
  title,
  subtitle,
  startFrame = 0,
  durationInFrames = 200,
}) => {
  const currentFrame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const relFrame = currentFrame - startFrame;
  if (relFrame < 0 || relFrame > durationInFrames) {
    return null;
  }

  const enter = spring({
    frame: relFrame,
    fps,
    config: { damping: 15, mass: 0.9 },
  });

  const exit = interpolate(
    relFrame,
    [durationInFrames - 25, durationInFrames],
    [1, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    }
  );

  const opacity = enter * exit;
  const slideX = interpolate(enter, [0, 1], [-80, 0]);

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 55,
        left: 55,
        zIndex: 90,
        opacity,
        transform: `translateX(${slideX}px)`,
        fontFamily: 'Inter, system-ui, sans-serif',
        userSelect: 'none',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: 'rgba(10, 15, 26, 0.92)',
          backdropFilter: 'blur(20px)',
          padding: '12px 24px',
          borderRadius: 14,
          border: '1px solid rgba(99, 220, 255, 0.28)',
          boxShadow:
            '0 15px 40px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.1)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 4,
          }}
        >
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: '#57dfbc',
              boxShadow: '0 0 10px #57dfbc',
            }}
          />
          <span
            style={{
              fontSize: 10,
              fontWeight: 800,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: '#57dfbc',
            }}
          >
            {chapter}
          </span>
        </div>
        <div
          style={{
            fontSize: 18,
            fontWeight: 800,
            color: '#f8fafc',
            letterSpacing: '-0.02em',
          }}
        >
          {title}
        </div>
        {subtitle && (
          <div
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: '#94a3b8',
              marginTop: 3,
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
    </div>
  );
};
