import {FPS} from '../theme.js';
import {Scene01, beat as beat01} from './Scene01.jsx';
import {Scene02, beat as beat02} from './Scene02.jsx';
import {Scene03, beat as beat03} from './Scene03.jsx';
import {Scene04, beat as beat04} from './Scene04.jsx';
import {Scene05, beat as beat05} from './Scene05.jsx';
import {Scene06, beat as beat06} from './Scene06.jsx';
import {Scene07, beat as beat07} from './Scene07.jsx';
import {Scene08, beat as beat08} from './Scene08.jsx';
import {Scene09, beat as beat09} from './Scene09.jsx';
import {Scene10, beat as beat10} from './Scene10.jsx';

export const scenes = [
  {id: 'Scene01', component: Scene01, frames: beat01.seconds * FPS},
  {id: 'Scene02', component: Scene02, frames: beat02.seconds * FPS},
  {id: 'Scene03', component: Scene03, frames: beat03.seconds * FPS},
  {id: 'Scene04', component: Scene04, frames: beat04.seconds * FPS},
  {id: 'Scene05', component: Scene05, frames: beat05.seconds * FPS},
  {id: 'Scene06', component: Scene06, frames: beat06.seconds * FPS},
  {id: 'Scene07', component: Scene07, frames: beat07.seconds * FPS},
  {id: 'Scene08', component: Scene08, frames: beat08.seconds * FPS},
  {id: 'Scene09', component: Scene09, frames: beat09.seconds * FPS},
  {id: 'Scene10', component: Scene10, frames: beat10.seconds * FPS},
];
