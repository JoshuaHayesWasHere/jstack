import React from 'react';
import {Composition} from 'remotion';
import {Film, filmFrames} from './Film.jsx';
import {scenes} from './scenes/index.js';
import {FPS, HEIGHT, WIDTH} from './theme.js';

export const Root = () => (
  <>
    <Composition id="Film" component={Film} width={WIDTH} height={HEIGHT} fps={FPS} durationInFrames={filmFrames} />
    {scenes.map(({id, component, frames}) => (
      <Composition key={id} id={id} component={component} width={WIDTH} height={HEIGHT} fps={FPS} durationInFrames={frames} />
    ))}
  </>
);
