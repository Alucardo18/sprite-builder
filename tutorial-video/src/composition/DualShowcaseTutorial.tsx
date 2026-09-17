import React from 'react';
import { linearTiming, TransitionSeries } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import { slide } from '@remotion/transitions/slide';
import { ShowcaseSceneIntro } from '../scenes/ShowcaseSceneIntro';
import { ShowcaseSceneSprites } from '../scenes/ShowcaseSceneSprites';
import { ShowcaseSceneStudio } from '../scenes/ShowcaseSceneStudio';
import { ShowcaseSceneBlob47 } from '../scenes/ShowcaseSceneBlob47';
import { ShowcaseSceneDualGrid } from '../scenes/ShowcaseSceneDualGrid';
import { ShowcaseSceneMapExport } from '../scenes/ShowcaseSceneMapExport';

export const DualShowcaseTutorial: React.FC = () => {
  return (
    <TransitionSeries>
      {/* Escena 1: Introducción a la Suite Integrada (1140 frames ~ 19.0s) */}
      <TransitionSeries.Sequence durationInFrames={1140}>
        <ShowcaseSceneIntro />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 2: Sprite Builder Workflow: Fondo, Alineación y Cortes (1520 frames ~ 25.3s) */}
      <TransitionSeries.Sequence durationInFrames={1520}>
        <ShowcaseSceneSprites />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={slide({ direction: 'from-right' })}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 3: Estudio de Animación con Reproductor en Vivo (GIF Loop) (1240 frames ~ 20.7s) */}
      <TransitionSeries.Sequence durationInFrames={1240}>
        <ShowcaseSceneStudio />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 4: Tileset Builder · Algoritmo Blob 47 (1300 frames ~ 21.7s) */}
      <TransitionSeries.Sequence durationInFrames={1300}>
        <ShowcaseSceneBlob47 />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={slide({ direction: 'from-right' })}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 5: Tileset Builder · Dual Grid 15 Rápido (1240 frames ~ 20.7s) */}
      <TransitionSeries.Sequence durationInFrames={1240}>
        <ShowcaseSceneDualGrid />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 30 })}
      />

      {/* Escena 6: Map Tester y Exportación Lista para Motores (1160 frames ~ 19.3s) */}
      <TransitionSeries.Sequence durationInFrames={1160}>
        <ShowcaseSceneMapExport />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
