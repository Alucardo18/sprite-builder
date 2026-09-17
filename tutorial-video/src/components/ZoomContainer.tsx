import React from 'react';
import { interpolate, useCurrentFrame } from 'remotion';

interface ZoomKeyframe {
  frame: number;
  scale: number;
  x: number; // percentage (-50% to +50%) or px offset
  y: number;
}

interface ZoomContainerProps {
  children: React.ReactNode;
  keyframes?: ZoomKeyframe[];
  scale?: number;
  panX?: number;
  panY?: number;
  originX?: string;
  originY?: string;
}

export const ZoomContainer: React.FC<ZoomContainerProps> = ({
  children,
  keyframes,
  scale: staticScale,
  panX: staticPanX,
  panY: staticPanY,
  originX = '50%',
  originY = '50%',
}) => {
  const currentFrame = useCurrentFrame();

  let scale = staticScale ?? 1;
  let panX = staticPanX ?? 0;
  let panY = staticPanY ?? 0;

  if (keyframes && keyframes.length >= 2) {
    const frameSteps = keyframes.map((k) => k.frame);
    const scaleSteps = keyframes.map((k) => k.scale);
    const xSteps = keyframes.map((k) => k.x);
    const ySteps = keyframes.map((k) => k.y);

    scale = interpolate(currentFrame, frameSteps, scaleSteps, {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });

    panX = interpolate(currentFrame, frameSteps, xSteps, {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });

    panY = interpolate(currentFrame, frameSteps, ySteps, {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        transformOrigin: `${originX} ${originY}`,
        transform: `translate3d(${panX}px, ${panY}px, 0) scale(${scale})`,
        transition: 'transform 0.05s linear',
        willChange: 'transform',
      }}
    >
      {children}
    </div>
  );
};
