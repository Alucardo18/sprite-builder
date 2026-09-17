import React from 'react';
import { linearTiming, TransitionSeries } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import { slide } from '@remotion/transitions/slide';
import { SpriteSceneIntro } from '../scenes/SpriteSceneIntro';
import { SpriteSceneBackground } from '../scenes/SpriteSceneBackground';
import { SpriteScenePrepare } from '../scenes/SpriteScenePrepare';
import { SpriteSceneAlign } from '../scenes/SpriteSceneAlign';
import { SpriteSceneExport } from '../scenes/SpriteSceneExport';

export const SpriteBuilderTutorial: React.FC = () => {
  return (
    <TransitionSeries>
      {/* Escena 1: Introducción a Sheet Studio (1480 frames ~ 24.6s) */}
      <TransitionSeries.Sequence durationInFrames={1480}>
        <SpriteSceneIntro />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 2: Remoción de Fondo y Limpieza (1520 frames ~ 25.3s) */}
      <TransitionSeries.Sequence durationInFrames={1520}>
        <SpriteSceneBackground />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={slide({ direction: 'from-right' })}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 3: Preparar Poses y Asignación de Frames (1360 frames ~ 22.6s) */}
      <TransitionSeries.Sequence durationInFrames={1360}>
        <SpriteScenePrepare />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 4: Alineación Multi-Anchor (1620 frames ~ 27.0s) */}
      <TransitionSeries.Sequence durationInFrames={1620}>
        <SpriteSceneAlign />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={slide({ direction: 'from-bottom' })}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 5: Cortes Finales y Exportación (1540 frames ~ 25.6s) */}
      <TransitionSeries.Sequence durationInFrames={1540}>
        <SpriteSceneExport />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
