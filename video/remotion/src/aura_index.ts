import React from 'react';
import {registerRoot, Composition} from 'remotion';
import {AuraFilm} from './aura/Aura';
const Root: React.FC = () => React.createElement(Composition as any, {id: 'AuraFilm', component: AuraFilm, width: 1920, height: 1080, fps: 30, durationInFrames: 85 * 30});
registerRoot(Root);
