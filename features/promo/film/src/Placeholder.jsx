import React from 'react';
import {AbsoluteFill} from 'remotion';
import {colour, type} from './theme.js';

export const Placeholder = ({beat}) => (
  <AbsoluteFill style={{backgroundColor: colour.ink, justifyContent: 'center', alignItems: 'center', gap: 24}}>
    <div style={{fontFamily: type.serif, fontStyle: 'italic', fontSize: 240, lineHeight: 1, color: colour.amber}}>
      {beat.number}
    </div>
    <div style={{fontFamily: type.grotesk, fontSize: 72, fontWeight: 600, color: colour.text}}>{beat.name}</div>
    <div style={{fontFamily: type.grotesk, fontSize: 40, color: colour.mute}}>{beat.seconds} s</div>
  </AbsoluteFill>
);
