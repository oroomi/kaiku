import React from 'react';
import {Composition} from 'remotion';
import {Film} from './Film';
import {ApprovalFilm} from './ApprovalFilm';
import {BODY_FRAMES} from './scenes';
export const Root: React.FC = () => (
  <><Composition id="Approval" component={ApprovalFilm} width={1920} height={1080} fps={30} durationInFrames={3902} />
  <Composition id="KaikuBody" component={Film} width={1920} height={1080} fps={30} durationInFrames={BODY_FRAMES} defaultProps={{qr: ''}} /></>
);
