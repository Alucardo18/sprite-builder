import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

interface CalloutBadgeProps {
  step?: string;
  title: string;
  description: string;
  icon?: string;
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
  startFrame?: number;
  durationInFrames?: number;
}

export const CalloutBadge: React.FC<CalloutBadgeProps> = ({
  step,
  title,
  description,
  icon = '💡',
  position = 'top-right',
  startFrame = 0,
  durationInFrames = 240,
}) => {
  const currentFrame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const relFrame = currentFrame - startFrame;
  if (relFrame < 0 || relFrame > durationInFrames) {
    return null;
  }

  // Entrance spring animation
  const enterProgress = spring({
    frame: relFrame,
    fps,
    config: { damping: 14, mass: 0.8 },
  });

  // Exit fade animation
  const exitProgress = interpolate(
    relFrame,
    [durationInFrames - 30, durationInFrames],
    [1, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    }
  );

  const opacity = enterProgress * exitProgress;
  const translateY = interpolate(enterProgress, [0, 1], [-20, 0]);

  const posStyle: React.CSSProperties = {
    position: 'absolute',
    zIndex: 100,
    ...(position === 'top-right' && { top: 70, right: 40 }),
    ...(position === 'top-left' && { top: 70, left: 40 }),
    ...(position === 'bottom-right' && { bottom: 50, right: 40 }),
    ...(position === 'bottom-left' && { bottom: 50, left: 40 }),
  };

  return (
    <div
      style={{
        ...posStyle,
        opacity,
        transform: `translateY(${translateY}px) scale(${0.9 + enterProgress * 0.1})`,
        width: 360,
        borderRadius: 16,
        padding: '16px 20px',
        backgroundColor: 'rgba(15, 23, 42, 0.88)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(87, 223, 188, 0.35)',
        boxShadow:
          '0 20px 50px rgba(0, 0, 0, 0.65), 0 0 25px rgba(87, 223, 188, 0.2)',
        fontFamily: 'Inter, system-ui, sans-serif',
        color: '#f8fafc',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: 20 }}>{icon}</span>
        {step && (
          <span
            style={{
              fontSize: 10,
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              padding: '3px 8px',
              borderRadius: 20,
              backgroundColor: 'rgba(87, 223, 188, 0.18)',
              color: '#57dfbc',
              border: '1px solid rgba(87, 223, 188, 0.3)',
            }}
          >
            {step}
          </span>
        )}
      </div>
      <div
        style={{
          fontSize: 15,
          fontWeight: 700,
          color: '#ffffff',
          marginBottom: 6,
          letterSpacing: '-0.01em',
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontSize: 12,
          lineHeight: 1.5,
          color: '#94a3b8',
        }}
      >
        {description}
      </div>
    </div>
  );
};
