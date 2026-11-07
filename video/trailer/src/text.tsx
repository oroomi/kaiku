import React from 'react';
import {continueRender, delayRender, staticFile} from 'remotion';
import {hex, rgba} from './lib';

export const FAMILY = 'ManropeKR';
const WEIGHT = 700;

let fontReady = false;
export const useFont = () => {
  const [ok, setOk] = React.useState(fontReady);
  const [handle] = React.useState(() => (fontReady ? null : delayRender('font')));
  React.useEffect(() => {
    if (fontReady) {
      if (handle !== null) continueRender(handle);
      return;
    }
    const ff = new FontFace(FAMILY, `url(${staticFile('fonts/manrope-normal-0.woff2')})`, {weight: '200 800'});
    ff.load()
      .then((f) => {
        (document as any).fonts.add(f);
        fontReady = true;
        setOk(true);
        if (handle !== null) continueRender(handle);
      })
      .catch(() => {
        fontReady = true;
        setOk(true);
        if (handle !== null) continueRender(handle);
      });
  }, []);
  return ok;
};

let ctx: CanvasRenderingContext2D | null = null;
const cache = new Map<string, number>();
export const measure = (text: string, size = 100, weight = WEIGHT) => {
  const key = `${text}|${size}|${weight}`;
  const c = cache.get(key);
  if (c !== undefined) return c;
  if (!ctx) ctx = document.createElement('canvas').getContext('2d')!;
  ctx.font = `${weight} ${size}px ${FAMILY}`;
  const w = ctx.measureText(text).width;
  cache.set(key, w);
  return w;
};

export type WordState = {y?: number; scale?: number; op?: number; blur?: number; dx?: number; rot?: number};

export type LineProps = {
  words: string[];
  state: (i: number) => WordState;
  /** target total width (px) of the line at gapEm0 and zero tracking: font size is derived from it */
  fitWidth: number;
  gapEm0?: number;
  gapEm: number; // current gap in em
  lsEm?: number; // current letter spacing in em
  cx?: number;
  cy: number;
  stops: [number, string][];
  glow?: string[]; // shadow colours [tight, mid, wide]
  glowAmt?: number;
  weight?: number;
};

export const lineSize = (words: string[], fitWidth: number, gapEm0: number, weight = WEIGHT) => {
  const w100 = words.reduce((s, w) => s + measure(w, 100, weight), 0) + gapEm0 * 100 * (words.length - 1);
  return (fitWidth / w100) * 100;
};

export const LitLine: React.FC<LineProps> = ({words, state, fitWidth, gapEm0 = 0.3, gapEm, lsEm = 0, cx = 960, cy, stops, glow, glowAmt = 1, weight = WEIGHT}) => {
  const size = lineSize(words, fitWidth, gapEm0, weight);
  const ls = lsEm * size;
  const widths = words.map((w) => measure(w, size, weight) + ls * w.length);
  const gap = gapEm * size;
  const total = widths.reduce((a, b) => a + b, 0) + gap * (words.length - 1);
  let x = cx - total / 2;
  const g = glow ?? ['rgba(255,255,255,0.7)', 'rgba(255,90,200,0.5)', 'rgba(110,90,255,0.45)'];
  const gradient = `linear-gradient(90deg, ${stops.map(([p, c]) => `${c} ${p * 100}%`).join(',')})`;
  return (
    <>
      {words.map((w, i) => {
        const st = state(i);
        const left = x + (st.dx ?? 0);
        const off = x - (cx - total / 2);
        x += widths[i] + gap;
        const op = st.op ?? 1;
        if (op <= 0.001) return null;
        const common: React.CSSProperties = {
          fontFamily: FAMILY,
          fontWeight: weight,
          fontSize: size,
          letterSpacing: ls,
          lineHeight: 1,
          whiteSpace: 'nowrap',
          position: 'absolute',
          left: 0,
          top: 0,
        };
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left,
              top: cy,
              width: widths[i],
              height: size,
              transform: `translateY(${-size / 2 + (st.y ?? 0)}px) scale(${st.scale ?? 1}) rotate(${st.rot ?? 0}deg)`,
              transformOrigin: '50% 55%',
              opacity: Math.min(1, op),
              filter: st.blur && st.blur > 0.3 ? `blur(${st.blur}px)` : undefined,
            }}
          >
            <div
              style={{
                ...common,
                color: 'rgba(255,255,255,0.01)',
                textShadow: `0 0 ${size * 0.1}px ${g[0]}, 0 0 ${size * 0.3}px ${g[1].replace(/[\d.]+\)$/, (m) => String(parseFloat(m) * glowAmt) + ')')}, 0 0 ${size * 0.7}px ${g[2].replace(/[\d.]+\)$/, (m) => String(parseFloat(m) * glowAmt) + ')')}`,
              }}
            >
              {w}
            </div>
            <div
              style={{
                ...common,
                color: 'transparent',
                backgroundImage: gradient,
                backgroundSize: `${total}px 100%`,
                backgroundPosition: `${-off}px 0`,
                backgroundRepeat: 'no-repeat',
                WebkitBackgroundClip: 'text',
                backgroundClip: 'text',
              }}
            >
              {w}
            </div>
          </div>
        );
      })}
    </>
  );
};

export const Blob: React.FC<{x: number; y: number; r: number; c: string; a: number}> = ({x, y, r, c, a}) =>
  a <= 0.01 ? null : (
    <div
      style={{
        position: 'absolute',
        left: x - r,
        top: y - r,
        width: r * 2,
        height: r * 2,
        borderRadius: '50%',
        background: `radial-gradient(closest-side, ${rgba(hex(c), a)} 0%, ${rgba(hex(c), a * 0.45)} 38%, ${rgba(hex(c), 0)} 100%)`,
      }}
    />
  );

export const lineExtent = (words: string[], fitWidth: number, gapEm0: number, gapEm: number, lsEm: number, cx = 960, weight = WEIGHT) => {
  const size = lineSize(words, fitWidth, gapEm0, weight);
  const ls = lsEm * size;
  const widths = words.map((w) => measure(w, size, weight) + ls * w.length);
  const total = widths.reduce((a, b) => a + b, 0) + gapEm * size * (words.length - 1);
  return {size, left: cx - total / 2, right: cx + total / 2, total};
};
