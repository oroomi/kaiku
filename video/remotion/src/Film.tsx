import React from 'react';
import {AbsoluteFill, Sequence, OffthreadVideo, Img, staticFile, useCurrentFrame, interpolate, spring, useVideoConfig, Easing} from 'remotion';
import {SCENES, FPS, Scene, Cap} from './scenes';

const font = `@font-face{font-family:'Manrope';src:url(${staticFile('fonts/manrope-normal-0.woff2')}) format('woff2');font-weight:200 800;}`;
const BG = 'radial-gradient(1200px 700px at 50% 35%, #14323f 0%, #0a161d 55%, #05090c 100%)';

const CaptionPill: React.FC<{cap: Cap; size: number; big?: boolean}> = ({cap, size, big}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const a = Math.round(cap.a * FPS), b = Math.round(cap.b * FPS);
  if (f < a || f > b) return null;
  const pop = spring({frame: f - a, fps, config: {damping: 13, stiffness: 190, mass: 0.7}});
  const out = interpolate(f, [b - 5, b], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const sc = interpolate(pop, [0, 1], [0.86, 1]);
  return (
    <div style={{transform: `scale(${sc})`, opacity: Math.min(1, pop * 1.4) * out, transformOrigin: big ? 'left center' : 'center'}}>
      <div style={{display: 'inline-block', padding: big ? '0' : '14px 34px 16px', borderRadius: 18, background: big ? 'none' : 'rgba(6,12,16,0.82)', border: big ? 'none' : '1px solid rgba(143,211,232,0.35)',
        color: '#fff', fontWeight: 700, fontSize: size, lineHeight: 1.12, letterSpacing: -0.5, }}>{cap.text}</div>
    </div>
  );
};

const Pop: React.FC<{children: React.ReactNode}> = ({children}) => {
  const f = useCurrentFrame();
  const t = interpolate(f, [0, 12], [0, 1], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const flash = interpolate(f, [0, 3, 10], [0.0, 0.28, 0], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{background: BG}}>
      <AbsoluteFill style={{transform: t < 1 ? `scale(${1.05 - 0.05 * t})` : undefined, opacity: Math.min(1, t * 1.6), filter: t < 1 ? `blur(${(1 - t) * 10}px)` : undefined}}>{children}</AbsoluteFill>
      {flash > 0.003 && <AbsoluteFill style={{background: '#cfeaf5', opacity: flash}} />}
    </AbsoluteFill>
  );
};

const Chip: React.FC<{small?: boolean}> = ({small}) => (
  <div style={{position: 'absolute', right: small ? 10 : 18, top: small ? 10 : 18, padding: '6px 16px', borderRadius: 14, background: 'rgba(255,210,122,0.92)', color: '#1a1405', fontWeight: 800, fontSize: small ? 22 : 26, letterSpacing: 0.5}}>SAMPLE DATA</div>
);

// slow push-in on a region of the page (the voice placeholder zooms to the orb)
const Zoomed: React.FC<{s: Scene; children: React.ReactNode}> = ({s, children}) => {
  const f = useCurrentFrame();
  if (!s.zoom) return <>{children}</>;
  const k = interpolate(f, [0, Math.round(s.dur * FPS)], [1, s.zoom.s], {extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)});
  return <div style={{width: 1664, height: 936, transformOrigin: `${s.zoom.ox * 100}% ${s.zoom.oy * 100}%`, transform: `scale(${k})`}}>{children}</div>;
};

const Desk: React.FC<{s: Scene}> = ({s}) => (
  <Pop>
    <div style={{position: 'absolute', left: 128, top: 22, width: 1664, height: 936, borderRadius: 22, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.16)', background: '#000'}}>
      <Zoomed s={s}><OffthreadVideo src={staticFile(s.src!)} startFrom={Math.round((s.from ?? 0) * FPS)} muted playbackRate={s.rate ?? 1} style={{width: 1664, height: 936, objectFit: 'contain'}} /></Zoomed>
      {s.sample && <Chip />}
    </div>
    <div style={{position: 'absolute', left: 0, right: 0, top: 976, display: 'flex', justifyContent: 'center'}}>
      <div style={{position: 'relative', height: 90, width: 1800, display: 'flex', justifyContent: 'center'}}>
        <div style={{position: 'absolute'}}>{s.caps.map((c) => <CaptionPill key={c.id} cap={c} size={54} />)}</div>
      </div>
    </div>
  </Pop>
);

const Phone: React.FC<{s: Scene}> = ({s}) => {
  const f = useCurrentFrame();
  const tap = (s.tap ?? -999) * FPS;
  const k = f - tap;
  const ring = k >= 0 && k < 18 ? interpolate(k, [0, 18], [0, 1]) : -1;
  const SC = 1.1, W = 390 * SC, H = 844 * SC;
  return (
    <Pop>
      <div style={{position: 'absolute', left: 300, top: (1080 - H) / 2 - 6, width: W + 24, height: H + 24, borderRadius: 58, background: '#020304', border: '2px solid rgba(255,255,255,0.22)', padding: 12}}>
        <div style={{position: 'relative', width: W, height: H, borderRadius: 46, overflow: 'hidden'}}>
          {s.still ? <Img src={staticFile(s.src!)} style={{width: W, height: H, objectFit: 'contain', background: '#000'}} /> : <OffthreadVideo src={staticFile(s.src!)} startFrom={Math.round((s.from ?? 0) * FPS)} muted style={{width: W, height: H}} />}
          {s.sample && <Chip small />}
          {ring >= 0 && <div style={{position: 'absolute', left: 195 * SC - 40, top: 434 * SC - 40, width: 80, height: 80, borderRadius: 40, border: '4px solid rgba(255,255,255,0.9)', transform: `scale(${0.4 + ring * 1.6})`, opacity: 1 - ring}} />}
        </div>
      </div>
      <div style={{position: 'absolute', left: 860, top: 0, width: 960, height: 1080, display: 'flex', alignItems: 'center'}}>
        <div style={{position: 'relative', width: 960, height: 400}}>
          {s.caps.map((c) => <div key={c.id} style={{position: 'absolute', left: 0, top: 120}}><CaptionPill cap={c} size={78} big /></div>)}
        </div>
      </div>
    </Pop>
  );
};

const Trailer: React.FC<{s: Scene}> = ({s}) => (
  <AbsoluteFill style={{background: '#000'}}><OffthreadVideo src={staticFile(s.src!)} muted style={{width: 1920, height: 1080}} /></AbsoluteFill>
);

const End: React.FC<{qr: string}> = ({qr}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = (_d: number) => 1; // v3: the end card is held completely still from its first frame (no entrance motion)
  const row = (d: number, node: React.ReactNode) => <div style={{opacity: p(d), transform: `translateY(${(1 - p(d)) * 24}px)`}}>{node}</div>;
  return (
    <AbsoluteFill style={{background: BG, color: '#fff', fontWeight: 700}}>
      <div style={{position: 'absolute', left: 130, top: 150, width: 1040}}>
        {row(0, <div style={{fontSize: 150, letterSpacing: -4}}>Kaiku</div>)}
        <div style={{height: 22}} />
        {row(8, <div style={{fontSize: 58, lineHeight: 1.15}}>Connect suggests.<br />The customer approves.</div>)}
        <div style={{height: 30}} />
        {row(16, <div style={{fontSize: 66, color: '#8fd3e8', whiteSpace: 'nowrap'}}>kaiku.hankintaviikko.fi</div>)}
        <div style={{height: 44}} />
        {row(26, <div style={{fontSize: 30, color: '#cfe6ee', fontWeight: 600, lineHeight: 1.3}}>Furry Paw Vet Clinic is a fictional<br />Fonecta sandbox entity.</div>)}
        <div style={{height: 22}} />
        {row(34, <div style={{fontSize: 34, color: '#a9c9d6', fontWeight: 600}}>Team VY7</div>)}
      </div>
      <div style={{position: 'absolute', right: 120, top: 190, opacity: p(20), transform: `scale(${0.9 + 0.1 * p(20)})`}}>
        <div style={{background: '#fff', padding: 64, boxSizing: 'border-box', borderRadius: 26, width: 592, height: 592}}>
          <img src={staticFile(qr)} style={{width: 464, height: 464, imageRendering: 'pixelated'}} />
        </div>
        <div style={{marginTop: 26, fontSize: 34, textAlign: 'center', width: 592, color: '#cfe6ee', fontWeight: 600}}>Scan: own one Turku business</div>
      </div>
    </AbsoluteFill>
  );
};

export const Film: React.FC<{qr: string}> = ({qr}) => {
  let at = 0;
  return (
    <AbsoluteFill style={{background: '#000', fontFamily: 'Manrope, sans-serif'}}>
      <style>{font}</style>
      {SCENES.map((s) => {
        const d = Math.round(s.dur * FPS); const from = at; at += d;
        return (
          <Sequence key={s.id} from={from} durationInFrames={d}>
            {s.kind === 'desk' && <Desk s={s} />}
            {s.kind === 'phone' && <Phone s={s} />}
            {s.kind === 'trailer' && <Trailer s={s} />}
            {s.kind === 'end' && <End qr={qr} />}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
