import React from 'react';
import { linearTiming, TransitionSeries } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import { slide } from '@remotion/transitions/slide';
import { SceneIntro } from '../scenes/SceneIntro';
import { SceneGrassDirt } from '../scenes/SceneGrassDirt';
import { SceneDirtWater } from '../scenes/SceneDirtWater';
import { SceneGrassWater } from '../scenes/SceneGrassWater';
import { SceneEcosystemOutro } from '../scenes/SceneEcosystemOutro';

export const TilesetBuilderTutorial: React.FC = () => {
  return (
    <TransitionSeries>
      {/* Escena 1: Introducción al Ecosistema (1480 frames ~ 24.6s) */}
      <TransitionSeries.Sequence durationInFrames={1480}>
        <SceneIntro />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 2: Patrón 1 · Pasto sobre Tierra (1540 frames ~ 25.6s) */}
      <TransitionSeries.Sequence durationInFrames={1540}>
        <SceneGrassDirt />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={slide({ direction: 'from-right' })}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 3: Patrón 2 · Tierra sobre Agua (1420 frames ~ 23.6s) */}
      <TransitionSeries.Sequence durationInFrames={1420}>
        <SceneDirtWater />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 4: Patrón 3 · Pasto sobre Agua (1340 frames ~ 22.3s) */}
      <TransitionSeries.Sequence durationInFrames={1340}>
        <SceneGrassWater />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={slide({ direction: 'from-bottom' })}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 5: Ecosistema Completo & Exportación (1560 frames ~ 26.0s) */}
      <TransitionSeries.Sequence durationInFrames={1560}>
        <SceneEcosystemOutro />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
