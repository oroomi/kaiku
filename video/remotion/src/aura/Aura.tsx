import React from 'react';
import {AbsoluteFill, Sequence, OffthreadVideo, Img, staticFile, useCurrentFrame, interpolate, spring, useVideoConfig, Easing} from 'remotion';
import caps from './captions.json';
import facts from '../../public/aura/facts.json';
import judge from '../../public/aura/judge.json';
import tools from '../../public/aura/mcp_tools.json';
import call from '../../public/aura/mcp_call.json';

const FPS = 30;
const S = (s: number) => Math.round(s * FPS);
const font = `@font-face{font-family:'Manrope';src:url(${staticFile('fonts/manrope-normal-0.woff2')}) format('woff2');font-weight:200 800;}`;
const BG = 'radial-gradient(1200px 700px at 50% 35%, #14323f 0%, #0a161d 55%, #05090c 100%)';
const CY = '#8fd3e8', AMB = '#ffd27a', GRN = '#9fe0b5';
const MONO = "'DejaVu Sans Mono','Noto Sans Mono',monospace";
const sc = (id: string) => caps.scenes.find((s) => s.id === id)!;
const cap = (id: string) => { for (const s of caps.scenes) for (const l of s.lines) if (l.id === id) return l; throw new Error(id); };
const hhmmss = (iso: string) => iso.slice(11, 19);

const useIn = (a: number, d = 14) => { const f = useCurrentFrame(); const {fps} = useVideoConfig(); return spring({frame: f - S(a), fps, config: {damping: 20, stiffness: 90, mass: 0.9}}); };

const Pill: React.FC<{id: string; size?: number; bottom?: number}> = ({id, size = 46, bottom = 96}) => {
  const f = useCurrentFrame(); const c = cap(id); const a = S(c.a), b = S(c.b);
  if (f < a || f > b) return null;
  const inn = interpolate(f, [a, a + 10], [0, 1], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const out = interpolate(f, [b - 8, b], [1, 0], {extrapolateLeft: 'clamp'});
  return (<div style={{position: 'absolute', left: 0, right: 0, bottom, display: 'flex', justifyContent: 'center', opacity: inn * out, transform: `translateY(${(1 - inn) * 14}px)`}}>
    <div style={{padding: '14px 36px 16px', borderRadius: 18, background: 'rgba(6,12,16,0.82)', border: '1px solid rgba(143,211,232,0.30)', color: '#fff', fontWeight: 600, fontSize: size, letterSpacing: -0.4, maxWidth: 1700, textAlign: 'center', lineHeight: 1.15}}>{c.text}</div>
  </div>);
};

const CLIP = 'aura/flight_lift2.mp4';
const Clip: React.FC<{start: number}> = ({start}) => (
  <AbsoluteFill>
    <OffthreadVideo src={staticFile(CLIP)} startFrom={start} muted style={{width: 1920, height: 1080}} />
    <AbsoluteFill style={{background: 'radial-gradient(1500px 850px at 50% 50%, rgba(5,9,12,0) 55%, rgba(5,9,12,0.45) 100%)'}} />
  </AbsoluteFill>
);
const hudAt = (fr: number) => { const hud: any[] = (facts as any).hud; let h = hud[0]; for (const x of hud) if (x.f <= fr) h = x; return h; };
const Hud: React.FC<{fr: number}> = ({fr}) => { const h = hudAt(fr); return (
  <div style={{position: 'absolute', left: 48, top: 40, fontFamily: MONO, color: '#cfe6ee', fontSize: 26, lineHeight: 1.5, background: 'rgba(6,12,16,0.72)', padding: '10px 20px', borderRadius: 12, border: '1px solid rgba(143,211,232,0.25)'}}>
    <div style={{color: CY, letterSpacing: 3}}>BROKER READ {hhmmss(h.ts)} UTC</div>
    <div>buses <b style={{color: CY}}>{h.buses}</b>  ships <b style={{color: AMB}}>{h.ships}</b></div>
  </div>); };

// scene 0-6: the answer first, on the populated map at the read that holds it (clip frame 570 = 23:36:49 UTC)
const Open: React.FC = () => {
  const f = useCurrentFrame(); const c = cap('c0'); const a = S(c.a);
  const inn = interpolate(f, [a, a + 12], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const out = interpolate(f, [S(5.3), S(5.9)], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (<AbsoluteFill><Clip start={570} /><Hud fr={570 + f} />
    <div style={{position: 'absolute', left: 0, right: 0, bottom: 110, display: 'flex', justifyContent: 'center', opacity: inn * out, transform: `translateY(${(1 - inn) * 20}px)`}}>
      <div style={{padding: '20px 54px 24px', borderRadius: 24, background: 'rgba(6,12,16,0.84)', border: '1px solid rgba(143,211,232,0.35)', color: '#fff', fontWeight: 700, fontSize: 92, letterSpacing: -2, lineHeight: 1.1}}>
        <span style={{color: AMB}}>43 m.</span> Closest ship to any bus.</div>
    </div></AbsoluteFill>);
};

// scene 6-46: the flight, three slaps over its first seconds, footer only after 18 s
const Flight: React.FC = () => {
  const f = useCurrentFrame(); const abs = f + S(6);
  const lines = ['o1', 'o2', 'o3'].map(cap);
  const fadeOut = interpolate(f, [S(38.8), S(40)], [1, 0], {extrapolateLeft: 'clamp'});
  const slapOut = interpolate(abs, [S(13.0), S(13.6)], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const footIn = interpolate(abs, [S(18.2), S(19)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{background: '#05090c', opacity: fadeOut}}>
      <Clip start={0} />
      <Hud fr={f} />
      <div style={{position: 'absolute', left: 90, bottom: 120, opacity: slapOut}}>
        {lines.map((l, i) => { const a = S(l.a); const t = interpolate(abs, [a, a + 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.6))});
          return <div key={l.id} style={{fontSize: 128, fontWeight: 800, letterSpacing: -4, color: '#fff', lineHeight: 1.08, opacity: t, transform: `translateX(${(1 - t) * -60}px) scale(${0.9 + 0.1 * t})`, transformOrigin: 'left center', textShadow: '0 4px 30px rgba(0,0,0,0.9), 0 0 6px rgba(0,0,0,0.8)'}}>{l.text}</div>; })}
      </div>
      <div style={{position: 'absolute', right: 40, bottom: 24, opacity: footIn, fontFamily: MONO, color: 'rgba(255,255,255,0.6)', fontSize: 18, background: 'rgba(5,9,12,0.5)', padding: '4px 12px', borderRadius: 8}}>Map: OpenFreeMap, OpenStreetMap. Time-lapse of kaiku.hankintaviikko.fi/aura</div>
      {['f1', 'f4', 'f5', 'f6', 'f7'].map((id) => <FPill key={id} id={id} off={S(6)} />)}
    </AbsoluteFill>
  );
};
const FPill: React.FC<{id: string; off: number}> = ({id, off}) => { const c = cap(id); return <Shift id={id} off={off} c={c} />; };
const Shift: React.FC<{id: string; off: number; c: any}> = ({c, off}) => {
  const f = useCurrentFrame() + off; const a = S(c.a), b = S(c.b);
  if (f < a || f > b) return null;
  const inn = interpolate(f, [a, a + 10], [0, 1], {extrapolateRight: 'clamp'}); const out = interpolate(f, [b - 8, b], [1, 0], {extrapolateLeft: 'clamp'});
  return (<div style={{position: 'absolute', left: 0, right: 0, bottom: 60, display: 'flex', justifyContent: 'center', opacity: inn * out}}>
    <div style={{padding: '14px 36px 16px', borderRadius: 18, background: 'rgba(6,12,16,0.82)', border: '1px solid rgba(143,211,232,0.30)', color: '#fff', fontWeight: 600, fontSize: 46, letterSpacing: -0.4, textAlign: 'center', lineHeight: 1.15}}>{c.text}</div></div>);
};

const Sources: React.FC = () => {
  const p = useIn(0.2);
  const row = (d: number, name: string, what: string, lic: string, col: string) => { const q = useIn(d);
    return (<div style={{display: 'flex', alignItems: 'baseline', gap: 28, padding: '20px 0', borderBottom: '1px solid rgba(143,211,232,0.18)', opacity: q, transform: `translateY(${(1 - q) * 20}px)`}}>
      <div style={{width: 250, color: col, fontWeight: 700, fontSize: 36}}>{what}</div>
      <div style={{flex: 1, color: '#fff', fontWeight: 600, fontSize: 36}}>{name}</div>
      <div style={{fontFamily: MONO, color: '#a9c9d6', fontSize: 28}}>{lic}</div></div>); };
  const wx: any = (facts as any).weather;
  return (
    <AbsoluteFill style={{background: BG}}>
      <div style={{position: 'absolute', left: 150, top: 130, width: 1620, opacity: p, transform: `translateY(${(1 - p) * 30}px)`, background: 'rgba(5,9,12,0.8)', border: '1px solid rgba(143,211,232,0.25)', borderRadius: 24, padding: '30px 56px 34px', boxSizing: 'border-box'}}>
        <div style={{fontFamily: MONO, color: CY, fontSize: 28, letterSpacing: 3, marginBottom: 6}}>THE PAGE'S OWN SOURCES ROW</div>
        {row(0.5, 'Föli, data.foli.fi/siri/vm', 'Buses', 'CC BY 4.0', AMB)}
        {row(0.8, 'Fintraffic Digitraffic, AIS', 'Ships', 'CC BY 4.0', AMB)}
        {row(1.1, 'Open-Meteo: 5.6 °C, wind 3 m/s', 'Weather', 'CC BY 4.0', AMB)}
        {row(1.4, 'OpenFreeMap, OpenStreetMap', 'Map', 'ODbL', AMB)}
        <div style={{fontFamily: MONO, color: '#a9c9d6', fontSize: 28, marginTop: 24, lineHeight: 1.4}}>Live page at {hhmmss((facts as any).panel_ts)} UTC: {wx.entities} entities in the broker, {wx.buses} buses, {wx.ships} ships, {wx.weather} weather.</div>
      </div>
      <Pill id="s1" />
    </AbsoluteFill>
  );
};

// equirectangular scatter of the broker read that holds the closest pair
const BOX = {x0: 22.14, x1: 22.36, y0: 60.418, y1: 60.472};
const Scatter: React.FC<{w: number; h: number}> = ({w, h}) => {
  const f = useCurrentFrame(); const k = Math.cos((60.45 * Math.PI) / 180);
  const sx = w / ((BOX.x1 - BOX.x0) * k); const sy = h / (BOX.y1 - BOX.y0); const s = Math.min(sx, sy);
  const ox = (w - (BOX.x1 - BOX.x0) * k * s) / 2;
  const P = (lon: number, lat: number) => [ox + (lon - BOX.x0) * k * s, (BOX.y1 - lat) * s];
  const snap = (facts as any).snapshot; const b = (facts as any).best;
  const appear = interpolate(f, [S(0.2), S(1.5)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const pair = interpolate(f, [S(2.0), S(3.0)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const sp = P(...(b.ship_lonlat as [number, number])), bp = P(...(b.bus_lonlat as [number, number]));
  return (
    <svg width={w} height={h} style={{borderRadius: 22, background: 'rgba(6,12,16,0.7)', border: '1px solid rgba(143,211,232,0.25)'}}>
      {snap.buses.map((q: number[], i: number) => { const [x, y] = P(q[0], q[1]); return <circle key={'b' + i} cx={x} cy={y} r={9} fill={CY} opacity={appear * 0.85 * Math.min(1, appear * 3 - (i % 7) * 0.05)} />; })}
      {snap.ships.map((q: number[], i: number) => { const [x, y] = P(q[0], q[1]); return <rect key={'s' + i} x={x - 9} y={y - 9} width={18} height={18} transform={`rotate(45 ${x} ${y})`} fill={AMB} opacity={appear * 0.95} />; })}
      <line x1={sp[0]} y1={sp[1]} x2={sp[0] + (bp[0] - sp[0]) * pair} y2={sp[1] + (bp[1] - sp[1]) * pair} stroke="#fff" strokeWidth={3} />
      <circle cx={sp[0]} cy={sp[1]} r={20 * pair + 6} fill="none" stroke={AMB} strokeWidth={3} opacity={pair} />
      <circle cx={bp[0]} cy={bp[1]} r={20 * pair + 6} fill="none" stroke={CY} strokeWidth={3} opacity={pair} />
    </svg>
  );
};

const Question: React.FC = () => {
  const f = useCurrentFrame(); const b = (facts as any).best;
  const bgIn = interpolate(f, [0, 12], [0, 1], {extrapolateRight: 'clamp'});
  const res = interpolate(f, [S(3.2), S(4.0)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const nIn = (facts as any).near1km;
  return (
    <AbsoluteFill style={{background: BG, opacity: bgIn}}>
      <div style={{position: 'absolute', left: 90, top: 60}}><Scatter w={1080} h={640} /></div>
      <div style={{position: 'absolute', left: 90, top: 716, fontFamily: MONO, color: '#cfe6ee', fontSize: 28, width: 1080, lineHeight: 1.4}}>
        Broker read {hhmmss(b.ts)} UTC: <span style={{color: CY}}>{facts.snapshot.buses.length} buses</span>, <span style={{color: AMB}}>{facts.snapshot.ships.length} ships</span>. Bus: dot, ship: diamond.
      </div>
      <div style={{position: 'absolute', left: 1230, top: 90, width: 640, opacity: res, transform: `translateY(${(1 - res) * 20}px)`}}>
        <div style={{fontFamily: MONO, color: CY, fontSize: 28, letterSpacing: 3}}>CLOSEST SHIP TO ANY BUS</div>
        <div style={{fontSize: 230, fontWeight: 700, color: '#fff', letterSpacing: -7, lineHeight: 1}}>{b.distance_m}<span style={{fontSize: 96, color: AMB}}> m</span></div>
        <div style={{fontSize: 40, fontWeight: 600, color: '#e3f2f7', lineHeight: 1.3, marginTop: 10}}>Line {b.bus_line} to {b.bus_dest}<br />and the ship {b.ship_name}</div>
        <div style={{fontSize: 32, fontWeight: 600, color: '#cfe6ee', lineHeight: 1.35, marginTop: 24}}>{nIn} of {facts.snapshot.ships.length} ships have a bus within 1 km.</div>
      </div>
      <Pill id="q2" size={38} bottom={50} />
      <Pill id="q3" size={42} bottom={50} />
    </AbsoluteFill>
  );
};

const Broker: React.FC = () => {
  const f = useCurrentFrame(); const e: any = (judge as any).entity;
  const lines = [
    '{', `  "id": "${e.id}",`, `  "type": "${e.type}",`, `  "vehicleType": "${e.vehicleType.value}",`, `  "name": "${e.name.value}",`,
    `  "lineRef": "${e.lineRef.value}",`,
    `  "location": {"type":"GeoProperty", "coordinates": [${e.location.value.coordinates.join(', ')}],`, `    "observedAt": "${e.location.observedAt}"},`,
    `  "speed": {"value": ${e.speed.value}, "unitCode": "${e.speed.unitCode}"},`, `  "source": "${e.source.value}"`, '}'];
  const full = lines.join('\n');
  const blk = interpolate(f, [S(0.5), S(1.0)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const t2 = useIn(1.2);
  return (
    <AbsoluteFill style={{background: BG}}>
      <div style={{position: 'absolute', left: 90, top: 90, width: 1240, height: 700, opacity: blk, background: 'rgba(5,9,12,0.85)', border: '1px solid rgba(143,211,232,0.25)', borderRadius: 22, padding: '30px 44px', boxSizing: 'border-box'}}>
        <div style={{fontFamily: MONO, color: '#a9c9d6', fontSize: 24, marginBottom: 14}}>GET /api/aura/judge, entity read from Orion-LD, {hhmmss((judge as any).fetched)} UTC</div>
        <pre style={{fontFamily: MONO, fontSize: 31, color: '#dff3f9', lineHeight: 1.38, margin: 0, whiteSpace: 'pre-wrap'}}>{full}</pre>
      </div>
      <div style={{position: 'absolute', left: 1380, top: 150, width: 480, color: '#fff', fontWeight: 700, opacity: t2, transform: `translateY(${(1 - t2) * 24}px)`}}>
        <div style={{fontSize: 60, lineHeight: 1.12, letterSpacing: -1}}>FIWARE<br />Orion-LD</div>
        <div style={{fontSize: 34, color: CY, marginTop: 20, fontWeight: 600}}>NGSI-LD</div>
        <div style={{fontSize: 34, color: AMB, marginTop: 8, fontWeight: 600}}>datasetId on every instance</div>
        <div style={{fontSize: 28, color: '#cfe6ee', marginTop: 26, fontWeight: 500, lineHeight: 1.4}}>Each vehicle carries source and observedAt.</div>
      </div>
      <Pill id="b1" size={40} bottom={60} />
    </AbsoluteFill>
  );
};

const Mcp: React.FC = () => {
  const f = useCurrentFrame(); const T: any[] = (tools as any).tools; const A: any = (call as any).answer; const E: any[] = A.entities;
  const nS = E.filter((x) => x.vehicleType.value === 'vessel').length, nB = E.filter((x) => x.vehicleType.value === 'bus').length;
  const reqO = interpolate(f, [S(0.2), S(0.6)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const reqText = `query_entities(\n  type: "Vehicle",\n  georel: "${(call as any).args.georel}",\n  geometry: "Point",\n  coordinates: "${(call as any).args.coordinates}")`;
  const ansO = interpolate(f, [S(3.0), S(3.4)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const box = {background: 'rgba(5,9,12,0.85)', border: '1px solid rgba(143,211,232,0.25)', borderRadius: 22, boxSizing: 'border-box' as const};
  return (
    <AbsoluteFill style={{background: BG}}>
      <div style={{position: 'absolute', left: 90, top: 70, width: 860, height: 520, ...box, padding: '26px 40px', opacity: reqO}}>
        <div style={{fontFamily: MONO, color: '#a9c9d6', fontSize: 24, marginBottom: 14, lineHeight: 1.35}}>Direct call to Gateway.query_entities, the function behind the MCP tool (not stdio), {hhmmss((call as any).ts)} UTC</div>
        <pre style={{fontFamily: MONO, fontSize: 30, color: '#dff3f9', lineHeight: 1.45, margin: 0, whiteSpace: 'pre-wrap'}}>{reqText}</pre>
        <div style={{fontFamily: MONO, color: '#a9c9d6', fontSize: 24, marginTop: 14}}>read-only GET to Orion-LD, harbour 60.4335 N, 22.2189 E</div>
      </div>
      <div style={{position: 'absolute', left: 990, top: 70, width: 840, height: 520, ...box, padding: '26px 40px', opacity: ansO}}>
        <div style={{fontFamily: MONO, color: GRN, fontSize: 26, letterSpacing: 2, marginBottom: 10}}>ANSWER FROM THE BROKER</div>
        <div style={{fontSize: 150, fontWeight: 700, color: '#fff', letterSpacing: -5, lineHeight: 1}}>{A.count}<span style={{fontSize: 48, color: '#cfe6ee', letterSpacing: 0, fontWeight: 600}}>  entities</span></div>
        <div style={{fontSize: 44, fontWeight: 600, marginTop: 8}}><span style={{color: AMB}}>{nS} ships</span>, <span style={{color: CY}}>{nB} bus</span></div>
        <div style={{fontFamily: MONO, fontSize: 24, color: '#cfe6ee', marginTop: 18, lineHeight: 1.5}}>
          {E.slice(0, 3).map((x) => <div key={x.id}>{x.id.replace('urn:ngsi-ld:Vehicle:', '')}  {x.name?.value}  [{x.vehicleType.datasetId}]</div>)}<div>...</div></div>
      </div>
      <div style={{position: 'absolute', left: 90, top: 630, width: 1740, display: 'flex', flexWrap: 'wrap', gap: 14, opacity: ansO}}>
        {T.map((t) => <div key={t.name} style={{fontFamily: MONO, fontSize: 24, color: t.name === 'query_entities' ? '#05090c' : CY, background: t.name === 'query_entities' ? CY : 'rgba(143,211,232,0.10)', padding: '8px 16px', borderRadius: 12}}>{t.name}</div>)}
      </div>
      <Pill id="m1" size={44} bottom={60} />
      <Pill id="m2" size={44} bottom={60} />
    </AbsoluteFill>
  );
};

const End: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const p = (d: number) => spring({frame: f - d, fps, config: {damping: 16, stiffness: 120}});
  const row = (d: number, n: React.ReactNode) => <div style={{opacity: p(d), transform: `translateY(${(1 - p(d)) * 22}px)`}}>{n}</div>;
  return (
    <AbsoluteFill style={{background: BG, color: '#fff', fontWeight: 700}}>
      <div style={{position: 'absolute', left: 140, top: 190, width: 1060}}>
        {row(0, <div style={{fontSize: 160, letterSpacing: -5}}>Aura</div>)}
        <div style={{height: 20}} />
        {row(10, <div style={{fontSize: 54, color: '#cfe6ee', fontWeight: 600}}>Turku, live, in one broker.</div>)}
        <div style={{height: 34}} />
        {row(20, <div style={{fontSize: 64, color: CY, whiteSpace: 'nowrap'}}>kaiku.hankintaviikko.fi/aura</div>)}
        <div style={{height: 46}} />
        {row(32, <div style={{fontSize: 38, color: '#cfe6ee', fontWeight: 600, lineHeight: 1.3}}>Team VY7, Since AI 2026, FIWARE track</div>)}
        <div style={{height: 14}} />
        {row(40, <div style={{fontSize: 26, color: '#8fa9b4', fontWeight: 500}}>Föli, Fintraffic Digitraffic and Open-Meteo, all CC BY 4.0</div>)}
      </div>
      <div style={{position: 'absolute', right: 150, top: 220, opacity: p(18), transform: `scale(${0.92 + 0.08 * p(18)})`}}>
        <div style={{background: '#fff', padding: 48, borderRadius: 26, width: 560, height: 560, boxSizing: 'border-box'}}><Img src={staticFile('aura/qr.png')} style={{width: 464, height: 464, imageRendering: 'pixelated'}} /></div>
        <div style={{marginTop: 22, fontSize: 30, textAlign: 'center', color: '#cfe6ee', fontWeight: 600}}>Scan: see Turku live</div>
      </div>
    </AbsoluteFill>
  );
};

export const AuraFilm: React.FC = () => (
  <AbsoluteFill style={{background: '#05090c', fontFamily: 'Manrope, sans-serif'}}>
    <style>{font}</style>
    <Sequence from={0} durationInFrames={S(6)}><Open /></Sequence>
    <Sequence from={S(6)} durationInFrames={S(40)}><Flight /></Sequence>
    <Sequence from={S(46)} durationInFrames={S(6)}><Sources /></Sequence>
    <Sequence from={S(52)} durationInFrames={S(10)}><Question /></Sequence>
    <Sequence from={S(62)} durationInFrames={S(9)}><Broker /></Sequence>
    <Sequence from={S(71)} durationInFrames={S(7)}><Mcp /></Sequence>
    <Sequence from={S(78)} durationInFrames={S(7)}><End /></Sequence>
  </AbsoluteFill>
);
