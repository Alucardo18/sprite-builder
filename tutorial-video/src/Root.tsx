import React from 'react';
import { Composition } from 'remotion';
import { TilesetBuilderTutorial } from './composition/TilesetBuilderTutorial';
import { SpriteBuilderTutorial } from './composition/SpriteBuilderTutorial';
import { DualShowcaseTutorial } from './composition/DualShowcaseTutorial';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TilesetBuilderTutorial"
        component={TilesetBuilderTutorial}
        durationInFrames={7220} // 120.33s @ 60fps
        fps={60}
        width={1920}
        height={1080}
      />
      <Composition
        id="SpriteBuilderTutorial"
        component={SpriteBuilderTutorial}
        durationInFrames={7400} // 123.33s @ 60fps
        fps={60}
        width={1920}
        height={1080}
      />
      <Composition
        id="DualShowcaseTutorial"
        component={DualShowcaseTutorial}
        durationInFrames={7450} // 124.16s @ 60fps
        fps={60}
        width={1920}
        height={1080}
      />
    </>
  );
};
