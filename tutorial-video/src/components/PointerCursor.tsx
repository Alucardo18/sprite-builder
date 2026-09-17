import React from 'react';
import { interpolate, useCurrentFrame } from 'remotion';

export interface CursorPoint {
  frame: number;
  x: number;
  y: number;
  click?: boolean;
}

interface PointerCursorProps {
  points?: CursorPoint[];
  visible?: boolean;
}

export const PointerCursor: React.FC<PointerCursorProps> = ({
  points = [],
  visible = true,
}) => {
  const currentFrame = useCurrentFrame();

  if (!visible || points.length === 0) {
    return null;
  }

  const frames = points.map((p) => p.frame);
  const xValues = points.map((p) => p.x);
  const yValues = points.map((p) => p.y);

  const x = interpolate(currentFrame, frames, xValues, {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const y = interpolate(currentFrame, frames, yValues, {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Determine if a click happened in the last 15 frames
  const recentClick = points.find(
    (p) => p.click && currentFrame >= p.frame && currentFrame <= p.frame + 18
  );

  const clickScale = recentClick
    ? interpolate(currentFrame, [recentClick.frame, recentClick.frame + 18], [0.5, 2.2], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      })
    : 1;

  const clickOpacity = recentClick
    ? interpolate(currentFrame, [recentClick.frame, recentClick.frame + 18], [0.9, 0], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      })
    : 0;

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        transform: `translate3d(${x}px, ${y}px, 0)`,
        pointerEvents: 'none',
        zIndex: 9999,
        willChange: 'transform',
      }}
    >
      {/* Click ripple animation */}
      {recentClick && (
        <div
          style={{
            position: 'absolute',
            top: -16,
            left: -16,
            width: 42,
            height: 42,
            borderRadius: '50%',
            border: '2px solid #57dfbc',
            backgroundColor: 'rgba(87, 223, 188, 0.35)',
            transform: `scale(${clickScale})`,
            opacity: clickOpacity,
            boxShadow: '0 0 15px rgba(87, 223, 188, 0.7)',
          }}
        />
      )}

      {/* SVG Modern Cursor */}
      <svg
        width="28"
        height="28"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{
          filter: 'drop-shadow(0 4px 10px rgba(0,0,0,0.65))',
        }}
      >
        <path
          d="M3 3L10.07 20.97L12.58 13.58L19.97 11.07L3 3Z"
          fill="#10b981"
          stroke="#ffffff"
          strokeWidth="2"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
};
