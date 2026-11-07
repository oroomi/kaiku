import React from 'react';
import {FAMILY} from './text';
import {K, KV, KC, seg, ss, eo3, eob, clamp} from './lib';
import {IconName, useSpec, usePalette} from './spec';

export type IconKind = IconName;

export const Icon: React.FC<{kind: IconKind; size: number; color?: string}> = ({kind, size, color = '#fff'}) => {
  const s = size;
  if (kind === 'play')
    return (
      <svg width={s} height={s} viewBox="0 0 24 24">
        <path d="M7 4.5v15a1 1 0 0 0 1.5.85l12-7.5a1 1 0 0 0 0-1.7l-12-7.5A1 1 0 0 0 7 4.5z" fill={color} />
      </svg>
    );
  if (kind === 'page')
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none">
        <path d="M6 2.5h8l5 5V20a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 20V4A1.5 1.5 0 0 1 6 2.5z" fill={color} />
        <path d="M14 2.5V8h5" stroke="rgba(0,0,0,0.35)" strokeWidth="1.4" />
        <path d="M8 12.5h8M8 16h8" stroke="rgba(0,0,0,0.4)" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  if (kind === 'receipt')
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none">
        <path d="M6 2.5h12a1 1 0 0 1 1 1V21l-2.4-1.7L14.2 21l-2.2-1.7L9.8 21l-2.4-1.7L5 21V3.5a1 1 0 0 1 1-1z" fill={color} />
        <path d="M8.2 7.5h7.6M8.2 11h7.6M8.2 14.5h4.4" stroke="rgba(0,0,0,0.4)" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  if (kind === 'anchor')
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="5.2" r="2.3" />
        <path d="M12 7.5V20.5" />
        <path d="M8.2 11H15.8" />
        <path d="M4 14.2c.4 3.6 3.6 6.3 8 6.3s7.6-2.7 8-6.3" />
        <path d="M4 14.2l-1.4 2.2M4 14.2l2.3 1M20 14.2l1.4 2.2M20 14.2l-2.3 1" />
      </svg>
    );
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill={color}>
      <rect x="2.5" y="10" width="2.6" height="4" rx="1.3" />
      <rect x="6.6" y="6" width="2.6" height="12" rx="1.3" />
      <rect x="10.7" y="3" width="2.6" height="18" rx="1.3" />
      <rect x="14.8" y="7.5" width="2.6" height="9" rx="1.3" />
      <rect x="18.9" y="10" width="2.6" height="4" rx="1.3" />
    </svg>
  );
};

/* ---------------- pills 2.2 - 4.0 ---------------- */
const PW = 590;
const PH = 152;
const PITCH = 214;

export const Pills: React.FC<{t: number}> = ({t}) => {
  const spec = useSpec();
  const pal = usePalette();
  const PILLS = spec.pills.map((p) => ({kind: p.icon, label: p.label}));
  if (t < 2.15 || t > 4.1) return null;
  return (
    <>
      {PILLS.map((p, i) => {
        const d = i * 0.07;
        const a = seg(t, 2.1 + d, 2.42 + d);
        const e = eo3(a);
        const x0 = 960 + 10;
        const exit = ss(seg(t, 3.55 + d * 0.5, 4.0));
        const pitch = PITCH * (0.25 + 0.75 * ss(seg(t, 2.1, 2.42))) * (1 - 0.65 * exit);
        const dx = (1 - e) * 600 - exit * 160;
        const sc = (0.72 + 0.28 * e) * (1 - 0.14 * exit);
        const op = Math.min(seg(t, 2.2 + d, 2.4 + d), 1 - seg(t, 3.7 + d * 0.5, 4.02));
        const cy = 528 + (i - 1) * pitch + Math.sin(t * 2.4 + i) * 3 * (1 - exit);
        const rot = (1 - e) * -9 + exit * 5;
        const lit = 0.75 + 0.25 * Math.sin(t * 5 + i * 1.3);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: x0 - PW / 2 + dx,
              top: cy - PH / 2,
              width: PW,
              height: PH,
              opacity: op,
              transform: `rotate(${rot}deg) scale(${sc})`,
              zIndex: 3 - i,
            }}
          >
            <div
              style={{
                position: 'absolute',
                inset: 0,
                borderRadius: PH / 2,
                background: `linear-gradient(90deg,${pal.pill[0]} 0%,${pal.pill[1]} 26%,${pal.pill[2]} 52%,${pal.pill[3]} 100%)`,
                border: '3px solid rgba(200,230,255,0.92)',
                boxShadow: `0 0 18px rgba(190,215,255,${0.8 * lit}), 0 0 46px rgba(255,90,220,${0.65 * lit}), 0 0 110px rgba(170,90,255,${0.45 * lit}), inset 0 0 22px rgba(255,255,255,0.25)`,
              }}
            />
            {/* highlights top / bottom */}
            <div style={{position: 'absolute', left: PW * 0.4, width: PW * 0.28, top: -9, height: 16, borderRadius: 8, background: 'rgba(255,255,255,0.8)', filter: 'blur(5px)'}} />
            <div style={{position: 'absolute', left: PW * 0.32, width: PW * 0.34, bottom: -8, height: 14, borderRadius: 8, background: 'rgba(255,255,255,0.6)', filter: 'blur(5px)'}} />
            {/* divider */}
            <div style={{position: 'absolute', left: PW * 0.265, top: 28, bottom: 28, width: 2, background: 'rgba(255,255,255,0.45)'}} />
            <div style={{position: 'absolute', left: 0, top: 0, width: PW * 0.265, height: PH, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
              <Icon kind={p.kind} size={62} />
            </div>
            <div
              style={{
                position: 'absolute',
                left: PW * 0.28,
                right: 0,
                top: 0,
                height: PH,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-start',
                paddingLeft: 36,
                fontFamily: FAMILY,
                fontWeight: 600,
                fontSize: spec.pillLabelSize ?? 54,
                color: '#fff',
                letterSpacing: 1,
                paddingBottom: 6,
              }}
            >
              {p.label}
            </div>
          </div>
        );
      })}
    </>
  );
};

/* ---------------- icon tiles (particles) ---------------- */
export const Tile: React.FC<{k: number; x: number; y: number; size: number; rx: number; ry: number; rz: number; op: number; glow?: number}> = ({k, x, y, size, rx, ry, rz, op, glow = 1}) => {
  const pal = usePalette();
  const kinds = useSpec().particles.icons;
  if (op <= 0.01 || size < 3) return null;
  return (
    <div style={{position: 'absolute', left: x - size / 2, top: y - size / 2, width: size, height: size, opacity: op, perspective: 600}}>
      <div
        style={{
          width: size,
          height: size,
          borderRadius: size * 0.26,
          background: pal.tiles[k],
          border: `${Math.max(2, size * 0.03)}px solid rgba(255,255,255,0.85)`,
          boxShadow: `0 0 ${size * 0.25}px ${size * 0.04}px rgba(190,140,255,${0.7 * glow}), 0 0 ${size * 0.7}px rgba(120,100,255,${0.5 * glow})`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transform: `rotateX(${rx}deg) rotateY(${ry}deg) rotateZ(${rz}deg)`,
          boxSizing: 'border-box',
        }}
      >
        <Icon kind={kinds[k]} size={size * 0.5} />
      </div>
    </div>
  );
};

/** text chip flying in as the third particle (used when the spec gives screen.flyer.chip): same gradient, rim, glow and tumble as a tile */
export const Chip: React.FC<{text: string; x: number; y: number; size: number; rx: number; ry: number; rz: number; op: number}> = ({text, x, y, size, rx, ry, rz, op}) => {
  const pal = usePalette();
  if (op <= 0.01 || size < 3) return null;
  const h = size * 0.62;
  return (
    <div style={{position: 'absolute', left: x, top: y - h / 2, height: h, opacity: op, perspective: 800, transform: 'translateX(-50%)', whiteSpace: 'nowrap'}}>
      <div
        style={{
          height: h,
          padding: `0 ${h * 0.5}px`,
          borderRadius: h / 2,
          background: pal.tiles[2],
          border: `${Math.max(2, size * 0.03)}px solid rgba(255,255,255,0.85)`,
          boxShadow: `0 0 ${size * 0.25}px ${size * 0.04}px rgba(190,140,255,0.7), 0 0 ${size * 0.7}px rgba(120,100,255,0.5)`,
          display: 'flex',
          alignItems: 'center',
          fontFamily: FAMILY,
          fontWeight: 700,
          fontSize: h * 0.44,
          color: '#fff',
          letterSpacing: 0.3,
          transform: `rotateX(${rx}deg) rotateY(${ry}deg) rotateZ(${rz}deg)`,
          boxSizing: 'border-box',
        }}
      >
        {text}
      </div>
    </div>
  );
};

// frame fraction keyframes per tile: [t, x, y, size(px), op]
const TK: number[][][] = [
  [[5.15, 0.32, 0.4, 0, 0], [5.25, 0.32, 0.38, 70, 1], [5.6, 0.33, 0.33, 90, 1], [6.0, 0.4, 0.5, 100, 1], [6.4, 0.4, 0.48, 124, 1], [6.6, 0.39, 0.49, 124, 1], [6.8, 0.37, 0.66, 122, 1], [7.0, 0.38, 0.63, 124, 1], [7.2, 0.44, 0.52, 128, 1], [7.4, 0.47, 0.28, 130, 1], [7.6, 0.485, 0.48, 120, 1], [7.85, 0.5, 0.55, 20, 0]],
  [[5.35, 0.5, 0.45, 0, 0], [5.45, 0.5, 0.4, 80, 1], [5.6, 0.5, 0.26, 85, 1], [6.0, 0.5, 0.57, 70, 1], [6.4, 0.5, 0.5, 118, 1], [6.6, 0.5, 0.5, 124, 1], [6.8, 0.5, 0.68, 122, 1], [7.0, 0.5, 0.6, 124, 1], [7.2, 0.5, 0.46, 128, 1], [7.4, 0.49, 0.28, 130, 1], [7.6, 0.49, 0.58, 120, 1], [7.85, 0.5, 0.58, 20, 0]],
  [[5.55, 0.68, 0.2, 0, 0], [5.65, 0.68, 0.16, 60, 1], [5.8, 0.67, 0.14, 85, 1], [6.0, 0.71, 0.42, 70, 1], [6.2, 0.65, 0.6, 80, 1], [6.4, 0.6, 0.5, 120, 1], [6.6, 0.6, 0.48, 124, 1], [6.8, 0.61, 0.64, 122, 1], [7.0, 0.63, 0.52, 124, 1], [7.2, 0.52, 0.38, 128, 1], [7.4, 0.5, 0.28, 130, 1], [7.6, 0.49, 0.72, 120, 1], [7.85, 0.5, 0.64, 20, 0]],
];
export const Tiles: React.FC<{t: number}> = ({t}) => {
  if (t < 5.1 || t > 7.9) return null;
  return (
    <>
      {[0, 1, 2].map((k) => {
        const [x, y, s0, o0] = KC(t, TK[k]); const s = Math.max(0, s0); const o = clamp(o0);
        const damp = 1 - 0.93 * ss(seg(t, 5.9, 6.3)) * (1 - ss(seg(t, 7.2, 7.5))) * 0.8 - 0.1 * ss(seg(t, 7.2, 7.5));
        const rx = 60 * Math.sin(t * 4.2 + k * 1.7) * damp;
        const ry = 70 * Math.cos(t * 3.4 + k * 2.1) * damp;
        const rz = 20 * Math.sin(t * 2 + k) * damp;
        return <Tile key={k} k={k} x={x * 1920} y={y * 1080} size={s} rx={rx} ry={ry} rz={rz} op={o} />;
      })}
    </>
  );
};
