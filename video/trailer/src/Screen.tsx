import React from 'react';
import {Img, staticFile} from 'remotion';
import {FAMILY} from './text';
import {K, KV, KC, seg, ss, eo3, eob, clamp, mixc, rgba} from './lib';
import {useSpec, PanelSpec} from './spec';

export const SW = 1700;
export const SH = 1300;
const CW = 380;
const CH = 340;
const GX = 56;
const GY = 128;
const GAP = 38;

/** camera rows: [t, fx, fy, ox, oy, s, ry, rx, rz]; keys from 9.6 s on were fitted by scripts/tune.mjs (SSIM vs the reference cells) and smoothed */
export const CAM: number[][] = [
  [9.0, -604.0, -300.0, 1900.0, 160.0, 1.75, 30.0, 0.0, 2.0],
  [9.4, -604.0, -300.0, 352.0, 78.0, 1.75, 24.0, 0.0, 2.0],
  [9.6, -604.0, -300.0, 146.78, 162.17, 1.74, 28.03, -5.0, 0.5],
  [10.0, -604.0, -300.0, 81.85, 159.17, 1.74, 25.73, -3.79, 0.12],
  [10.4, -604.0, -300.0, 37.68, 152.19, 1.7, 22.93, -2.57, -1.0],
  [10.8, -604.0, -300.0, 12.46, 155.72, 1.59, 18.03, -3.79, -1.38],
  [11.2, -604.0, -300.0, -4.61, 154.03, 1.56, 11.65, -3.07, 0.12],
  [11.6, -604.0, -300.0, -11.36, 135.75, 1.62, 8.58, 1.85, 1.23],
  [12.0, -604.0, -300.0, -33.43, 115.74, 1.57, 7.41, 3.07, 0.62],
  [12.4, -604.0, -300.0, -89.62, 102.41, 1.49, 7.31, 0.03, 0.25],
  [12.8, -606.42, -300.25, -205.44, 60.25, 1.47, 10.77, 1.65, 1.34],
  [13.0, -612.83, -300.91, -305.42, 21.76, 1.42, 12.69, 2.75, 1.61],
  [13.2, -620.78, -301.73, -413.62, -15.37, 1.34, 11.25, 5.41, 1.49],
  [13.4, -628.84, -302.59, -522.91, -44.97, 1.21, 5.08, 7.55, 1.59],
  [13.6, -620.49, -301.53, -601.05, -63.48, 1.15, 3.01, 8.16, 1.32],
  [13.8, -579.24, -296.74, -617.09, -68.42, 1.16, 5.54, 8.31, 0.71],
  [14.0, -500.51, -288.89, -567.9, -62.79, 1.14, 3.61, 13.87, 0.01],
  [14.2, -384.14, -279.08, -457.3, -50.36, 1.12, 1.57, 15.44, 0.06],
  [14.4, -254.64, -269.17, -320.92, -35.29, 1.11, 0.38, 14.59, 0.06],
  [14.6, -95.22, -261.6, -150.3, -17.56, 1.1, -2.4, 16.97, 0.2],
  [14.8, 15.93, -264.01, -30.46, -1.09, 1.11, -4.91, 20.74, 0.2],
  [15.0, 100.26, -276.01, 23.55, 28.61, 1.15, -5.88, 21.14, 0.22],
  [15.2, 171.71, -288.04, 26.37, 63.25, 1.18, -6.15, 15.2, 0.62],
  [15.4, 258.32, -297.23, 2.12, 72.95, 1.21, -5.04, 13.96, 0.07],
  [15.6, 358.73, -307.07, -5.4, 62.1, 1.24, -3.86, 13.4, 0.85],
  [15.8, 463.1, -317.39, -33.75, 90.0, 1.31, -4.76, 10.47, 1.67],
  [16.0, 541.33, -325.19, -66.78, 103.5, 1.45, -6.83, 5.47, 2.36],
  [16.2, 588.58, -329.47, -77.41, 139.5, 1.72, -8.88, 3.87, 2.4],
  [16.4, 608.86, -331.04, -50.75, 135.0, 1.77, -7.77, 6.1, 1.9],
  [16.6, 612.68, -331.17, -54.41, 72.0, 1.65, -5.95, 9.03, 0.9],
  [16.8, 612.21, -331.03, -296.78, -49.5, 1.75, -9.06, 17.02, -1.54],
  [17.0, 612.0, -331.0, -740.0, -22.5, 1.71, -16.75, 13.25, -4.25],
  [17.2, 612.0, -331.0, -1900.0, 0.0, 1.7, -32.0, 8.0, -8.0],
];

const RIM: number[][] = [
  [9.2, 210, 90, 255], [12.2, 190, 90, 255], [12.8, 255, 90, 115], [13.5, 255, 100, 125], [13.95, 170, 100, 255],
  [14.5, 120, 105, 255], [15.2, 70, 135, 255], [16.6, 60, 120, 255],
];

const APPEAR = [10.4, 10.45, 11.2, 11.7, 11.95, 12.15, 12.35, 12.55, 12.8, 13.0, 13.2, 13.4];

const Check: React.FC<{s: number}> = ({s}) => (
  <svg width={s} height={s} viewBox="0 0 24 24">
    <path d="M6 12.5l4 4 8-9" stroke="#fff" strokeWidth="3.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const CardView: React.FC<{i: number; t: number}> = ({i, t}) => {
  const scr = useSpec().screen;
  const c = scr.cards[i];
  const col = i % 4;
  const row = Math.floor(i / 4);
  const a = t - APPEAR[i];
  if (a < 0) return null;
  const grow = eob(clamp(a / 0.5), 1.6);
  const sc = i === 0 ? 0.4 + 0.6 * grow : 0.5 + 0.5 * grow;
  const op = clamp(a / 0.2);
  const fl = scr.flips.find((f) => f.card === i);
  const flip = fl ? ss(seg(t, fl.t, fl.t + 0.25)) : 0;
  const hot = clamp(1 - (a - (i === 0 ? 1.8 : 0.7)) / 1.2);
  const loading = i === 0 && t < 11.15;
  let label = c.status;
  if (loading) label = scr.loadingLabel;
  if (flip > 0.5) label = scr.flipLabel;
  const greenCol: [number, number, number] = [90, 245, 120];
  const violet: [number, number, number] = [170, 120, 255];
  const grey: [number, number, number] = [62, 63, 76];
  const rimBase = mixc(grey, violet, hot);
  const rim = mixc(rimBase, greenCol, flip);
  const glowA = 0.55 * hot + 0.75 * flip;
  const glowC = mixc(violet, greenCol, flip);
  const thumbOp = i === 0 ? ss(seg(t, 10.5, 10.9)) : 1;
  const bg = mixc([30, 31, 39], [22, 40, 30], flip);
  return (
    <div
      style={{
        position: 'absolute',
        left: GX + col * (CW + GAP),
        top: GY + row * (CH + GAP),
        width: CW,
        height: CH,
        borderRadius: 40,
        background: rgba(bg),
        border: `3px solid ${rgba(rim, 0.55 + 0.45 * Math.max(hot, flip))}`,
        boxShadow: `0 0 ${24 + 30 * flip}px ${4 * flip}px ${rgba(glowC, glowA)}, 0 0 ${70 + 50 * flip}px ${rgba(glowC, glowA * 0.45)}, inset 0 0 ${30 * flip}px ${rgba(greenCol, 0.2 * flip)}`,
        opacity: op,
        transform: `scale(${sc})`,
        boxSizing: 'border-box',
        padding: 22,
        fontFamily: FAMILY,
        color: '#fff',
      }}
    >
      <div style={{width: '100%', height: 176, borderRadius: 16, overflow: 'hidden', position: 'relative', background: '#0f1014', opacity: thumbOp, boxShadow: '0 4px 14px rgba(0,0,0,0.45)'}}>
        <Img
          src={staticFile(c.thumb)}
          style={{position: 'absolute', width: '100%', height: '100%', objectFit: 'cover', objectPosition: c.pos ?? '50% 50%', transform: `scale(${c.zoom ?? 1})`, filter: c.hue !== undefined ? `hue-rotate(${c.hue}deg) saturate(1.5) brightness(1.02) contrast(1.1)` : undefined}}
        />
      </div>
      <div style={{marginTop: 14, fontWeight: 700, fontSize: 24, letterSpacing: 0.2, ...(c.title.length > 22 ? {whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'} : {})}}>{c.title}</div>
      <div style={{display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 15, color: '#b4b6c2', fontWeight: 500}}>
        <span style={[].concat(c.sub as any).join('').length > 30 ? {whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginRight: 10} : undefined}>{c.sub}</span>
        <span style={{whiteSpace: 'nowrap'}}>{c.date}</span>
      </div>
      <div
        style={{
          position: 'absolute',
          left: 22,
          right: 22,
          bottom: 22,
          height: 46,
          borderRadius: 14,
          background: '#0d0e13',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 17,
          fontWeight: 600,
          color: '#fff',
          overflow: 'hidden',
        }}
      >
        {loading && <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: `${ss(seg(t, 10.55, 11.1)) * 100}%`, background: 'rgba(160,120,255,0.28)'}} />}
        <span style={{position: 'relative'}}>{label}</span>
      </div>
      {flip > 0.01 && (
        <div
          style={{
            position: 'absolute',
            left: -14,
            top: -14,
            width: 46,
            height: 46,
            borderRadius: 23,
            background: 'radial-gradient(circle at 35% 30%, #6bf58a, #26b843)',
            border: '2px solid rgba(255,255,255,0.8)',
            boxShadow: '0 0 20px rgba(80,255,120,0.9)',
            transform: `scale(${eob(flip, 2.4)})`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Check s={30} />
        </div>
      )}
    </div>
  );
};

const PanelView: React.FC<{p: PanelSpec; t: number; i: number}> = ({p, t, i}) => {
  const a = t - p.appear;
  if (a < 0) return null;
  const W = p.cw * CW + (p.cw - 1) * GAP, H = p.ch * CH + (p.ch - 1) * GAP;
  const grow = eob(clamp(a / 0.5), 1.6);
  const sc = i === 0 ? 0.4 + 0.6 * grow : 0.5 + 0.5 * grow;
  const op = clamp(a / 0.2);
  const flip = p.flip ? ss(seg(t, p.flip, p.flip + 0.25)) : 0;
  const hot = clamp(1 - (a - 0.9) / 1.2);
  const greenCol: [number, number, number] = [90, 245, 120];
  const violet: [number, number, number] = [170, 120, 255];
  const grey: [number, number, number] = [62, 63, 76];
  const rim = mixc(mixc(grey, violet, hot), greenCol, flip);
  const glowA = 0.55 * hot + 0.75 * flip;
  const glowC = mixc(violet, greenCol, flip);
  const label = flip > 0.5 ? useSpec().screen.flipLabel : p.label;
  return (
    <div style={{position: 'absolute', left: GX + p.col * (CW + GAP), top: GY + p.row * (CH + GAP), width: W, height: H, borderRadius: 40, background: rgba(mixc([30, 31, 39], [22, 40, 30], flip)),
      border: `3px solid ${rgba(rim, 0.55 + 0.45 * Math.max(hot, flip))}`, boxShadow: `0 0 ${24 + 30 * flip}px ${4 * flip}px ${rgba(glowC, glowA)}, 0 0 ${70 + 50 * flip}px ${rgba(glowC, glowA * 0.45)}`,
      opacity: op, transform: `scale(${sc})`, boxSizing: 'border-box', padding: 18, fontFamily: FAMILY, color: '#fff'}}>
      <div style={{width: '100%', height: H - 36 - 62, borderRadius: 22, overflow: 'hidden', position: 'relative', background: '#0f1014'}}>
        <Img src={staticFile(p.img)} style={{position: 'absolute', width: '100%', height: '100%', objectFit: 'cover', objectPosition: '50% 0%'}} />
      </div>
      <div style={{position: 'absolute', left: 18, right: 18, bottom: 16, height: 46, borderRadius: 14, background: '#0d0e13', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, fontWeight: 600}}>{label}</div>
      {flip > 0.01 && (
        <div style={{position: 'absolute', left: -14, top: -14, width: 46, height: 46, borderRadius: 23, background: 'radial-gradient(circle at 35% 30%, #6bf58a, #26b843)', border: '2px solid rgba(255,255,255,0.8)', boxShadow: '0 0 20px rgba(80,255,120,0.9)', transform: `scale(${eob(flip, 2.4)})`, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
          <Check s={30} />
        </div>
      )}
    </div>
  );
};

const AppUI: React.FC<{t: number}> = ({t}) => {
  const scr = useSpec().screen;
  const slotOp = 1 - ss(seg(t, 10.35, 10.6));
  const showShare = ss(seg(t, 13.3, 13.6));
  const flash = (1 - seg(t, 10.38, 10.85)) * (t > 10.38 ? 1 : 0);
  return (
    <div style={{position: 'absolute', inset: 0, background: '#15161c', fontFamily: FAMILY, color: '#fff'}}>
      {/* header */}
      <div style={{position: 'absolute', left: 0, right: 0, top: 0, height: 74, background: '#1c1d25', borderBottom: '1px solid rgba(255,255,255,0.05)'}} />
      <div style={{position: 'absolute', left: 56, top: 20, fontSize: 30, fontWeight: 800, letterSpacing: -0.5, display: 'flex', alignItems: 'center'}}>
        {scr.name}
        <span style={{width: 13, height: 13, borderRadius: 7, background: 'radial-gradient(circle at 35% 30%,#9fc8ff,#2d62e6)', marginLeft: 4, marginTop: 11, boxShadow: '0 0 10px #4f8cff'}} />
      </div>
      <div style={{position: 'absolute', left: 600, top: 20, width: 800, height: 34, borderRadius: 17, background: '#2b2c35', fontSize: 15, color: '#9a9cab', display: 'flex', alignItems: 'center', paddingLeft: 20, fontWeight: 500}}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#9a9cab" strokeWidth="2.4" strokeLinecap="round"><circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5L21 21" /></svg>
        <span style={{marginLeft: 10}}>{scr.searchPlaceholder}</span>
      </div>
      <div style={{position: 'absolute', right: 56, top: 16, display: 'flex', alignItems: 'center', gap: 16, opacity: showShare}}>
        {[0, 1, 2].map((k) => (
          <div key={k} style={{width: 38, height: 38, borderRadius: 12, background: '#2b2c35', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
            <div style={{width: 18, height: 18, borderRadius: k === 1 ? 9 : 4, border: '2.5px solid #b4b6c2'}} />
          </div>
        ))}
        <div style={{height: 38, padding: '0 24px', borderRadius: 19, background: 'linear-gradient(180deg,#2f6bff,#1b45d8)', fontSize: 17, fontWeight: 700, display: 'flex', alignItems: 'center', boxShadow: '0 0 18px rgba(70,120,255,0.6)'}}>{scr.actionButton}</div>
      </div>
      <div style={{position: 'absolute', left: 60, top: 88, fontSize: 19, color: '#c3c5d2', fontWeight: 600}}>{scr.breadcrumb}</div>

      {/* empty state slot */}
      {slotOp > 0.01 && (
        <div style={{position: 'absolute', left: GX, top: GY, width: CW, height: CH, borderRadius: 40, border: '3px dashed rgba(255,255,255,0.14)', background: 'rgba(255,255,255,0.025)', opacity: slotOp, boxSizing: 'border-box'}}>
          <div style={{position: 'absolute', left: 22, right: 22, bottom: 22, height: 46, borderRadius: 14, background: '#2b2c35', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: scr.uploadChip.length > 1 ? 19 : 30, fontWeight: 600, color: '#c3c5d2'}}>{scr.uploadChip}</div>
          {scr.emptyLabel && (
            <div style={{position: 'absolute', left: 30, right: 30, top: 24, bottom: 86, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', fontSize: 27, lineHeight: 1.28, fontWeight: 600, color: '#9a9cab'}}>{scr.emptyLabel}</div>
          )}
        </div>
      )}
      {flash > 0.01 && (
        <div style={{position: 'absolute', left: GX + CW / 2 - 400, top: GY + CH / 2 - 400, width: 800, height: 800, borderRadius: '50%', opacity: flash * 0.8, background: 'radial-gradient(closest-side, rgba(200,150,255,0.75), rgba(150,90,255,0.25) 50%, rgba(150,90,255,0))'}} />
      )}
      {scr.panels ? scr.panels.map((p, i) => <PanelView key={i} p={p} t={t} i={i} />) : scr.cards.map((_, i) => (
        <CardView key={i} i={i} t={t} />
      ))}
    </div>
  );
};

export const ScreenLayer: React.FC<{t: number; cam?: number[]}> = ({t, cam}) => {
  if (t < 8.9 || t > 17.3) return null;
  const [fx, fy, ox, oy, s, ry, rx, rz] = cam && cam.length === 8 ? cam : KC(t, CAM);
  const rim = KV(t, RIM, ss);
  const rimC: [number, number, number] = [rim[0], rim[1], rim[2]];
  const light = mixc(rimC, [255, 255, 255], 0.6);
  const other = mixc(rimC, [255, 90, 210], 0.35);
  const glow = 1;
  const enter = seg(t, 9.0, 9.5);
  const exitP = seg(t, 16.65, 17.2);
  const blurX = Math.max(0, (1 - enter) * (1 - enter) * 70 * (t < 9.6 ? 1 : 0), Math.sin(Math.PI * exitP) * 22 * (t > 16.6 ? 1 : 0));
  const R = 70;
  return (
    <div style={{position: 'absolute', inset: 0, opacity: 1 - 0.8 * seg(t, 16.95, 17.2), filter: blurX > 1 ? 'url(#mbx)' : undefined}}>
      <svg width="0" height="0" style={{position: 'absolute'}}>
        <filter id="mbx" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation={`${blurX} 0`} />
        </filter>
      </svg>
      <div style={{position: 'absolute', inset: 0, perspective: 1700, perspectiveOrigin: '50% 50%'}}>
        <div
          style={{
            position: 'absolute',
            left: 960 - SW / 2,
            top: 540 - SH / 2,
            width: SW,
            height: SH,
            transformOrigin: '50% 50%',
            transform: `translate3d(${ox}px,${oy}px,0) rotateX(${rx}deg) rotateY(${ry}deg) rotateZ(${rz}deg) scale(${s}) translate(${-fx}px,${-fy}px)`,
          }}
        >
          <div
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: R,
              padding: 7,
              boxSizing: 'border-box',
              background: `linear-gradient(135deg, ${rgba(light)} 0%, ${rgba(rimC)} 30%, ${rgba(other)} 100%)`,
              boxShadow: `0 0 14px 3px ${rgba(light, 0.9)}, 0 0 50px 12px ${rgba(rimC, 0.75 * glow)}, 0 0 120px 40px ${rgba(rimC, 0.5 * glow)}, 0 0 260px 90px ${rgba(rimC, 0.16 * glow)}`,
            }}
          >
            <div style={{position: 'relative', width: '100%', height: '100%', borderRadius: R - 7, overflow: 'hidden', background: '#15161c'}}>
              <AppUI t={t} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
