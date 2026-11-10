import React from 'react';
import {Series} from 'remotion';
import {scenes} from './scenes/index.js';

export const filmFrames = scenes.reduce((sum, scene) => sum + scene.frames, 0);

export const Film = () => (
  <Series>
    {scenes.map(({id, component: Scene, frames}) => (
      <Series.Sequence key={id} durationInFrames={frames}>
        <Scene />
      </Series.Sequence>
    ))}
  </Series>
);
