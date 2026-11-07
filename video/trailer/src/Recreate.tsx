import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {Stage} from './Stage';
import {Pills, Tiles, Tile, Chip} from './elements';
import {ScreenLayer} from './Screen';
import {Blob, LitLine, lineExtent, useFont, FAMILY} from './text';
import {K, KC, seg, ss, eo3, eob, clamp} from './lib';
import {DEFAULT_SPEC, Spec, SpecContext, OptsContext, useSpec, words, resolvePalette} from './spec';


const Line1: React.FC<{t: number}> = ({t}) => {
  const sp = useSpec().lines.l1;
  const L1 = {words: words(sp.text), fit: sp.fit, cy: sp.cy};
  if (t < 0.55 || t > 2.4) return null;
  const gap = K(t, [[1.2, 0.3], [2.3, 0.5]]);
  const ex = lineExtent(L1.words, L1.fit, 0.3, gap, 0);
  const exit = 1 - ss(seg(t, 1.95, 2.35));
  const lightL = ss(seg(t, 0.9, 1.4)) * exit;
  const lightR = ss(seg(t, 1.35, 1.8)) * exit;
  return (
    <>
      <Blob x={ex.left + 10} y={L1.cy - 12} r={95} c={sp.blobs![0]} a={0.75 * lightL} />
      <Blob x={ex.right - 20} y={L1.cy - 20} r={110} c={sp.blobs![1]} a={0.8 * lightR} />
      <LitLine
        words={L1.words}
        fitWidth={L1.fit}
        gapEm={gap}
        cy={L1.cy}
        stops={sp.stops}
        glow={sp.glow}
        glowAmt={K(t, [[0.6, 0.6], [1.6, 1.1], [2.2, 1]])}
        state={(i) => {
          const a = seg(t, 0.6 + 0.2 * i, 1.0 + 0.2 * i);
          return {y: (1 - eo3(a)) * 70, scale: (0.7 + 0.3 * eob(a, 2.2)) * (1 + 0.03 * (1 - exit)), op: Math.min(seg(a, 0, 0.35), exit), blur: (1 - exit) * 8 + (1 - a) * 4};
        }}
      />
    </>
  );
};

const Line2: React.FC<{t: number}> = ({t}) => {
  const sp = useSpec().lines.l2;
  const L2 = {words: words(sp.text), fit: sp.fit, cy: sp.cy};
  if (t < 3.85 || t > 6.0) return null;
  const gap = K(t, [[4.0, 0.3], [5.1, 1.3]]);
  const ls = K(t, [[4.0, 0], [5.1, 0.03]]);
  const ex = lineExtent(L2.words, L2.fit, 0.3, gap, ls);
  const enter = ss(seg(t, 3.8, 4.02));
  return (
    <>
      <Blob x={ex.left + 40} y={L2.cy - 8} r={90} c={sp.blobs![0]} a={0.55 * enter * (1 - ss(seg(t, 5.0, 5.5)))} />
      <Blob x={ex.right - 40} y={L2.cy - 8} r={100} c={sp.blobs![1]} a={0.6 * enter * (1 - ss(seg(t, 5.3, 5.9)))} />
      <LitLine
        words={L2.words}
        fitWidth={L2.fit}
        gapEm={gap}
        lsEm={ls}
        cy={L2.cy}
        stops={sp.stops}
        glow={sp.glow}
        glowAmt={0.9}
        state={(i) => {
          const d = 5.1 + 0.18 * i;
          const dis = seg(t, d, d + 0.28);
          return {op: Math.min(enter, 1 - dis), scale: (0.97 + 0.03 * enter) * (1 + 0.5 * dis), blur: (1 - enter) * 6 + dis * 12};
        }}
      />
    </>
  );
};

const Line3: React.FC<{t: number}> = ({t}) => {
  const sp = useSpec().lines.l3;
  const L3 = {words: words(sp.text), fit: sp.fit, cy: sp.cy};
  if (t < 7.65 || t > 9.4) return null;
  const gap = K(t, [[7.8, 0.3], [9.0, 0.42]]);
  const ex = lineExtent(L3.words, L3.fit, 0.3, gap, 0);
  const vis = K(t, [[8.7, 1], [9.0, 0.4], [9.3, 0]]);
  const lightA = ss(seg(t, 7.85, 8.2)) * vis;
  return (
    <>
      <Blob x={ex.left + 6} y={L3.cy + 4} r={90} c={sp.blobs![0]} a={0.9 * lightA} />
      <Blob x={ex.right - 30} y={L3.cy - 6} r={130} c={sp.blobs![1]} a={0.6 * lightA} />
      <LitLine
        words={L3.words}
        fitWidth={L3.fit}
        gapEm={gap}
        cy={L3.cy}
        stops={sp.stops}
        glow={sp.glow}
        glowAmt={1}
        state={(i) => {
          const a = seg(t, 7.7 + 0.06 * i, 8.15 + 0.06 * i);
          const lift = -i * 14 * (1 - ss(seg(t, 7.8, 8.7)));
          return {y: (1 - eo3(a)) * 40 + lift, scale: 0.9 + 0.1 * eob(a, 1.8), op: Math.min(seg(a, 0, 0.3), vis), blur: (1 - vis) * 10 + (1 - a) * 4};
        }}
      />
    </>
  );
};

const Flyer: React.FC<{t: number}> = ({t}) => {
  const fl = useSpec().screen.flyer;
  const chip = fl.chip;
  if (t < 9.5 || t > 10.65) return null;
  const rows = [
    [9.5, 0.0, 0.93, 120, 0],
    [9.6, 0.03, 0.84, 140, 1],
    [9.8, 0.26, 0.78, 150, 1],
    [10.0, 0.43, 0.6, 170, 1],
    [10.2, 0.48, 0.51, 180, 1],
    [10.4, 0.49, 0.5, 185, 1],
    [10.52, 0.49, 0.5, 90, 0.6],
    [10.62, 0.49, 0.52, 20, 0],
  ];
  const [x, y, s, o] = KC(t, rows);
  const trail = 0.4 * (1 - seg(t, 10.2, 10.45));
  if (fl.chips) {  // v3: the three contact pills fly in together, fan out at the start and converge on the first panel
    const conv = 1 - seg(t, 9.5, 10.25);
    return (
      <>
        {fl.chips.map((txt, k) => (
          <Chip key={k} text={txt} x={x * 1920 + (k - 1) * -170 * conv} y={y * 1080 + (k - 1) * 150 * conv} size={Math.max(0, s)} rx={12 * Math.sin(t * 6 + k)} ry={-14} rz={-8 + 10 * Math.sin(t * 5 + k)} op={clamp(o)} />
        ))}
      </>
    );
  }
  if (chip)
    return (
      <>
        <Chip text={chip} x={x * 1920 - 34 * trail * 2} y={y * 1080 + 24 * trail * 2} size={Math.max(0, s)} rx={20} ry={-10} rz={-8} op={clamp(o) * 0.55 * (trail > 0.02 ? 1 : 0)} />
        <Chip text={chip} x={x * 1920} y={y * 1080} size={Math.max(0, s)} rx={12 * Math.sin(t * 6)} ry={-14} rz={-8 + 10 * Math.sin(t * 5)} op={clamp(o)} />
      </>
    );
  return (
    <>
      <Tile k={0} x={x * 1920 - 34 * trail * 2} y={y * 1080 + 24 * trail * 2} size={Math.max(0, s)} rx={20} ry={-10} rz={-8} op={clamp(o) * 0.55 * (trail > 0.02 ? 1 : 0)} />
      <Tile k={2} x={x * 1920} y={y * 1080} size={Math.max(0, s)} rx={12 * Math.sin(t * 6)} ry={-14} rz={-8 + 10 * Math.sin(t * 5)} op={clamp(o)} />
    </>
  );
};

const Tagline: React.FC<{t: number}> = ({t}) => {
  const sp = useSpec().tagline;
  const L4 = {words: words(sp.text), fit: sp.fit, cy: sp.cy};
  const X = useSpec().timing?.extend ?? 0;
  if (t < 17.15 || t > 18.8 + X) return null;
  const exit = 1 - ss(seg(t, 18.2 + X, 18.55 + X));
  const stag = L4.words.length > 3 ? 0.62 / (L4.words.length - 1) : 0.2;
  const ex = lineExtent(L4.words, L4.fit, 0.3, 0.3, 0.01);
  const pulse = 0.85 + 0.15 * Math.sin(t * 7);
  return (
    <>
      <Blob x={ex.left + 20} y={L4.cy} r={110} c={sp.blobs![0]} a={0.85 * ss(seg(t, 17.25, 17.6)) * exit * pulse} />
      <Blob x={ex.right - 15} y={L4.cy} r={105} c={sp.blobs![1]} a={0.8 * ss(seg(t, 17.55, 17.9)) * exit * pulse} />
      <LitLine
        words={L4.words}
        fitWidth={L4.fit}
        gapEm={0.3}
        lsEm={0.01}
        cy={L4.cy}
        stops={sp.stops}
        glow={sp.glow}
        glowAmt={1.1}
        state={(i) => {
          const a = seg(t, 17.1 + stag * i, 17.4 + stag * i);
          return {scale: (0.8 + 0.2 * eob(a, 2.6)) * (1 + 0.04 * (1 - exit)), op: Math.min(seg(a, 0, 0.4), exit), blur: (1 - a) * 10 + (1 - exit) * 5, y: (1 - eo3(a)) * 18};
        }}
      />
    </>
  );
};

const Logo: React.FC<{t: number}> = ({t}) => {
  const sp = useSpec().logo;
  const L5 = {words: words(sp.text), fit: sp.fit, cy: 540};
  const X = useSpec().timing?.extend ?? 0;
  if (t < 18.25 + X) return null;
  const a = seg(t, 18.25 + X, 18.65 + X);
  const ex = lineExtent(L5.words, L5.fit, 0.3, 0.3, 0.03);
  const breathe = 0.9 + 0.1 * Math.sin(t * 2.2);
  return (
    <>
      <Blob x={960} y={L5.cy} r={420} c={sp.blob} a={0.22 * a * breathe} />
      <LitLine
        words={L5.words}
        fitWidth={L5.fit}
        gapEm={0.3}
        lsEm={0.03}
        cy={L5.cy}
        stops={sp.stops}
        glow={sp.glow}
        glowAmt={breathe * 1.2}
        state={() => ({scale: 1.1 - 0.1 * eo3(a), op: seg(a, 0, 0.5), blur: (1 - a) * 9})}
      />
      <div
        style={{
          position: 'absolute',
          left: ex.right + 10,
          top: L5.cy + ex.size * 0.08,
          width: 34,
          height: 34,
          borderRadius: 17,
          opacity: a,
          background: 'radial-gradient(circle at 35% 30%, #c0dcff, #3a6fff 60%, #2347c8)',
          boxShadow: '0 0 26px 8px rgba(80,130,255,0.85)',
        }}
      />
      {sp.url && (
        <div
          style={{
            position: 'absolute',
            left: 0,
            width: 1920,
            textAlign: 'center',
            top: L5.cy + ex.size * 0.5 + 44,
            opacity: ss(seg(t, 18.7 + X, 19.15 + X)) * 0.8,
            transform: `translateY(${(1 - ss(seg(t, 18.7 + X, 19.15 + X))) * 10}px)`,
            fontFamily: FAMILY,
            fontWeight: 600,
            fontSize: 34,
            letterSpacing: 2.5,
            color: '#dfe6ff',
            textShadow: '0 0 18px rgba(130,120,255,0.7)',
          }}
        >
          {sp.url}
        </div>
      )}
    </>
  );
};

export const Recreate: React.FC<{camOverride?: number[]; spec?: Spec; live?: boolean}> = ({camOverride, spec: specProp, live}) => {
  const frame = useCurrentFrame();
  const ok = useFont();
  const t = frame / 30;
  const spec = specProp ?? DEFAULT_SPEC;
  return (
    <SpecContext.Provider value={spec}>
    <OptsContext.Provider value={{sprites: !live}}>
    <AbsoluteFill style={{background: resolvePalette(spec.palette).bg}}>
      <Stage t={t} />
      {ok && (
        <>
          <Line1 t={t} />
          <Pills t={t} />
          <Line2 t={t} />
          <Tiles t={t} />
          <Line3 t={t} />
          <ScreenLayer t={t} cam={camOverride} />
          <Flyer t={t} />
          <Tagline t={t} />
          <Logo t={t} />
        </>
      )}
    </AbsoluteFill>
    </OptsContext.Provider>
    </SpecContext.Provider>
  );
};
