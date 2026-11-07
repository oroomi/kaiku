import React from 'react';
import {Composition} from 'remotion';
import {Recreate} from './Recreate';

export const TOTAL = 636; // 600 + 1.2 s (v3: longer closing line holds)

export const RemotionRoot: React.FC = () => (
  <Composition id="Recreate" component={Recreate} width={1920} height={1080} fps={30} durationInFrames={TOTAL} />
);
