import React from 'react';
import {AbsoluteFill, Sequence, OffthreadVideo, Img, staticFile, useCurrentFrame, interpolate, spring, useVideoConfig, Easing} from 'remotion';
// eslint-disable-next-line
declare const require: any;
const TL = require('./approval_timeline.json');
const FPS = 30;
const font = `@font-face{font-family:'Manrope';src:url(${staticFile('fonts/manrope-normal-0.woff2')}) format('woff2');font-weight:200 800;}`;
const BG = 'radial-gradient(1200px 700px at 50% 35%, #14323f 0%, #0a161d 55%, #05090c 100%)';
type Cap = {id: string; a: number; b: number; text: string};

const Pill: React.FC<{cap: Cap; size: number}> = ({cap, size}) => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const a = Math.round(cap.a * FPS), b = Math.round(cap.b * FPS);
  if (f < a || f > b) return null;
  const pop = spring({frame: f - a, fps, config: {damping: 13, stiffness: 190, mass: 0.7}});
  const out = interpolate(f, [b - 5, b], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (<div style={{position: 'absolute', transform: `scale(${interpolate(pop, [0, 1], [0.88, 1])})`, opacity: Math.min(1, pop * 1.4) * out}}>
    <div style={{display: 'inline-block', maxWidth: 1640, textAlign: 'center', padding: '12px 32px 14px', borderRadius: 18, background: 'rgba(6,12,16,0.86)', border: '1px solid rgba(143,211,232,0.35)', color: '#fff', fontWeight: 700, fontSize: size, lineHeight: 1.14, letterSpacing: -0.4}}>{cap.text}</div></div>);
};
const Caps: React.FC<{caps: Cap[]}> = ({caps}) => (
  <div style={{position: 'absolute', left: 0, right: 0, top: 972, height: 100, display: 'flex', justifyContent: 'center', alignItems: 'center'}}>
    <div style={{position: 'relative', width: 1700, height: 90, display: 'flex', justifyContent: 'center', alignItems: 'center'}}>{caps.map((c, i) => <Pill key={i} cap={c} size={42} />)}</div></div>);

const Pop: React.FC<{children: React.ReactNode}> = ({children}) => {
  const f = useCurrentFrame();
  const t = interpolate(f, [0, 12], [0, 1], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const flash = interpolate(f, [0, 3, 10], [0, 0.26, 0], {extrapolateRight: 'clamp'});
  return (<AbsoluteFill style={{background: BG}}>
    <AbsoluteFill style={{transform: t < 1 ? `scale(${1.05 - 0.05 * t})` : undefined, opacity: Math.min(1, t * 1.6), filter: t < 1 ? `blur(${(1 - t) * 10}px)` : undefined}}>{children}</AbsoluteFill>
    {flash > 0.003 && <AbsoluteFill style={{background: '#cfeaf5', opacity: flash}} />}</AbsoluteFill>);
};

const Tag: React.FC<{text: string}> = ({text}) => (<div style={{position: 'absolute', left: 150, top: 40, padding: '6px 14px', borderRadius: 999, background: 'rgba(6,12,16,0.72)', border: '1px solid rgba(255,210,122,0.55)', color: '#ffd27a', fontSize: 20, fontWeight: 700, letterSpacing: 2}}>{text}</div>);

const Desk: React.FC<{src: string; caps: Cap[]; tag?: string; children?: React.ReactNode; shift?: number}> = ({src, caps, tag, children, shift}) => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const k = shift ? spring({frame: f - Math.round(shift * FPS), fps, config: {damping: 16, stiffness: 120}}) : 0;
  return (<Pop>
    <div style={{position: 'absolute', left: 128, top: 22, width: 1664, height: 936, borderRadius: 22, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.16)', background: '#000', transform: `translateX(${-330 * k}px) scale(${1 - 0.2 * k})`, transformOrigin: 'left center'}}>
      <OffthreadVideo src={staticFile(src)} muted style={{width: 1664, height: 936, objectFit: 'cover'}} /></div>
    {tag && <Tag text={tag} />}
    {children}
    <Caps caps={caps} /></Pop>);
};

const Phone: React.FC<{src: string; caps: Cap[]}> = ({src, caps}) => {
  const SC = 1.1, W = 390 * SC, H = 844 * SC; const f = useCurrentFrame();
  const big = (a: number, b: number, text: string) => { const s = Math.round(a * FPS), e = Math.round(b * FPS); if (f < s || f > e) return null;
    const p = interpolate(f, [s, s + 8], [0, 1], {extrapolateRight: 'clamp'}); return <div style={{position: 'absolute', left: 0, top: 0, opacity: p * interpolate(f, [e - 5, e], [1, 0], {extrapolateLeft: 'clamp'}), transform: `translateY(${(1 - p) * 20}px)`, color: '#fff', fontWeight: 800, fontSize: 80, lineHeight: 1.08, letterSpacing: -1.5}}>{text}</div>; };
  return (<Pop>
    <div style={{position: 'absolute', left: 300, top: (1080 - H) / 2 - 6, width: W + 24, height: H + 24, borderRadius: 58, background: '#020304', border: '2px solid rgba(255,255,255,0.22)', padding: 12}}>
      <div style={{width: W, height: H, borderRadius: 46, overflow: 'hidden'}}><OffthreadVideo src={staticFile(src)} muted style={{width: W, height: H}} /></div></div>
    <div style={{position: 'absolute', left: 860, top: 380, width: 900}}>{big(0.4, 4.4, 'The same page fits a phone.')}{big(4.9, 7.4, 'Nothing to install.')}</div>
    <Caps caps={caps} /></Pop>);
};

const Reach: React.FC<{caps: Cap[]}> = ({caps}) => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const items = [{img: 'appr/phone_email.png', at: 0.2, label: '1  EMAIL'}, {img: 'appr/phone_wa.png', at: 4.4, label: '2  WHATSAPP'}, {img: 'appr/phone_call.png', at: 7.2, label: '3  CALL'}];
  const SC = 0.98, W = 390 * SC, H = 844 * SC;
  return (<Pop>
    {items.map((it, i) => { const p = spring({frame: f - Math.round(it.at * FPS), fps, config: {damping: 14, stiffness: 150}}); const x = 150 + i * 560;
      return (<div key={i} style={{position: 'absolute', left: x, top: 60, opacity: Math.min(1, p * 1.5), transform: `translateY(${(1 - p) * 70}px) scale(${0.92 + 0.08 * p})`}}>
        <div style={{color: '#8fd3e8', fontWeight: 800, fontSize: 30, letterSpacing: 3, marginBottom: 12, marginLeft: 12}}>{it.label}</div>
        <div style={{width: W + 20, height: H + 20, borderRadius: 52, background: '#020304', border: '2px solid rgba(255,255,255,0.22)', padding: 10}}>
          <div style={{width: W, height: H, borderRadius: 42, overflow: 'hidden'}}><Img src={staticFile(it.img)} style={{width: W, height: H}} /></div></div></div>); })}
    <Caps caps={caps} /></Pop>);
};

const Datasets: React.FC<{at: number}> = ({at}) => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  return (<div style={{position: 'absolute', left: 1180, top: 150, width: 700}}>
    <div style={{color: '#8fd3e8', fontWeight: 800, fontSize: 26, letterSpacing: 3, marginBottom: 14, opacity: spring({frame: f - Math.round(at * FPS), fps})}}>ONE ATTRIBUTE, ONE INSTANCE PER SOURCE</div>
    {TL.datasets.map((d: any, i: number) => { const p = spring({frame: f - Math.round((at + 0.25 + i * 0.35) * FPS), fps, config: {damping: 15, stiffness: 160}});
      return (<div key={i} style={{opacity: p, transform: `translateX(${(1 - p) * 40}px)`, marginBottom: 12, padding: '12px 18px', borderRadius: 14, background: 'rgba(6,12,16,0.86)', border: '1px solid rgba(143,211,232,0.35)'}}>
        <div style={{color: '#fff', fontWeight: 700, fontSize: 27}}>{d.source}</div><div style={{color: '#9fe0b5', fontSize: 21, fontFamily: 'IBM Plex Mono, monospace', marginTop: 3, wordBreak: 'break-all'}}>datasetId {d.id}</div></div>); })}</div>);
};

const Opener: React.FC = () => {
  const f = useCurrentFrame();
  const lines = ['Christmas Eve.', 'The clinic closes at one.', 'Google still says five.']; const slams = [0, 67, 124]; const hot = [-1, 'one', 'five'];
  const flash = slams.reduce((m, s) => Math.max(m, interpolate(f - s, [0, 2, 8], [0.0, 0.5, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})), 0);
  return (<AbsoluteFill style={{background: BG, color: '#fff', fontWeight: 800}}>
    {lines.map((t, i) => { if (f < slams[i]) return null;
      const k = f - slams[i]; const nxt = i < 2 ? slams[i + 1] - 6 : 9999; const shrink = interpolate(f, [nxt, nxt + 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
      const sl = interpolate(k, [0, 6], [1.45, 1], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)}); const op = interpolate(k, [0, 3], [0, 1], {extrapolateRight: 'clamp'});
      const blur = interpolate(k, [0, 6], [14, 0], {extrapolateRight: 'clamp'});
      const bigY = 540, kickY = 90 + i * 70; const y = bigY + (kickY - bigY) * shrink; const size = 150 - (150 - 44) * shrink;
      const parts = typeof hot[i] === 'string' ? t.split(hot[i] as string) : [t];
      return (<div key={i} style={{position: 'absolute', left: 0, right: 0, top: y - 90, textAlign: 'center', fontSize: size, letterSpacing: -4 + 3 * shrink, lineHeight: 1.05, opacity: op * (1 - 0.45 * shrink), transform: `scale(${sl})`, filter: `blur(${blur}px)`}}>
        {parts.length === 2 ? <>{parts[0]}<span style={{color: '#ffd27a'}}>{hot[i]}</span>{parts[1]}</> : t}</div>); })}
    {flash > 0.003 && <AbsoluteFill style={{background: '#cfeaf5', opacity: flash}} />}</AbsoluteFill>);
};

const End: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const p = (d: number) => spring({frame: f - d, fps, config: {damping: 14, stiffness: 160}});
  const row = (d: number, node: React.ReactNode) => <div style={{opacity: p(d), transform: `translateY(${(1 - p(d)) * 24}px)`}}>{node}</div>;
  const fade = interpolate(f, [Math.round(7.5 * FPS) - 14, Math.round(7.5 * FPS) - 1], [1, 0], {extrapolateLeft: 'clamp'});
  return (<AbsoluteFill style={{background: BG, opacity: fade, color: '#fff', fontWeight: 700}}>
    <div style={{position: 'absolute', left: 130, top: 170, width: 1100}}>
      {row(0, <div style={{fontSize: 150, letterSpacing: -4}}>Kaiku</div>)}<div style={{height: 20}} />
      {row(10, <div style={{fontSize: 64, lineHeight: 1.12, fontWeight: 800}}>Connect suggests.<br />The customer approves.</div>)}<div style={{height: 38}} />
      {row(22, <div style={{fontSize: 62, color: '#8fd3e8', whiteSpace: 'nowrap'}}>kaiku.hankintaviikko.fi</div>)}<div style={{height: 36}} />
      {row(32, <div style={{fontSize: 30, color: '#a9c9d6', fontWeight: 600, lineHeight: 1.3}}>Furry Paw Vet Clinic is a fictional Fonecta sandbox entity.<br />Team VY7</div>)}</div>
    <div style={{position: 'absolute', right: 130, top: 210, opacity: p(18), transform: `scale(${0.9 + 0.1 * p(18)})`}}>
      <div style={{background: '#fff', borderRadius: 26, width: 560, height: 560, display: 'grid', placeItems: 'center'}}><Img src={staticFile('qr_crop.png')} style={{width: 520, height: 520, imageRendering: 'pixelated'}} /></div>
      <div style={{marginTop: 22, fontSize: 32, textAlign: 'center', width: 560, color: '#cfe6ee', fontWeight: 600}}>Scan to try it</div></div></AbsoluteFill>);
};

export const ApprovalFilm: React.FC = () => (
  <AbsoluteFill style={{background: '#000', fontFamily: 'Manrope, sans-serif'}}><style>{font}</style>
    <Sequence from={0} durationInFrames={Math.round(TL.opener * FPS)}><Opener /></Sequence>
    {TL.beats.map((b: any) => (<Sequence key={b.id} from={Math.round(b.start * FPS)} durationInFrames={Math.round(b.dur * FPS)}>
      {b.id === 'A' && <Desk src="appr/A.mp4" caps={b.caps} tag="SAMPLE DATA" />}
      {b.id === 'B' && <Desk src="appr/B.mp4" caps={b.caps} tag="SAMPLE DATA" />}
      {b.id === 'C' && <Desk src="appr/C.mp4" caps={b.caps} tag="SAMPLE DATA" />}
      {b.id === 'D' && <Desk src="appr/D.mp4" caps={b.caps} tag="SAMPLE DATA" />}
      {b.id === 'P' && <Phone src="appr/P.mp4" caps={b.caps} />}
      {b.id === 'E' && <Reach caps={b.caps} />}
      {b.id === 'F' && <Desk src="appr/F.mp4" caps={b.caps} tag="LIVE FEED TEXT" />}
      {b.id === 'G' && <Desk src="appr/G.mp4" caps={b.caps} tag="LIVE JUDGE VIEW" shift={3.2}><Datasets at={3.6} /></Desk>}
      {b.id === 'H' && <End />}
    </Sequence>))}
  </AbsoluteFill>);
