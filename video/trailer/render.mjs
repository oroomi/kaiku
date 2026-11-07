// Bundle once, then render one or more compositions (or stills) with Remotion on a headless CPU-only box.
// Usage: node render.mjs --props props.json --browser /path/to/chrome-headless-shell --out-dir DIR
//          [--comp DemoH,DemoV] [--names demo_remotion.silent.mp4,demo_remotion_vertical.silent.mp4]
//          [--scale 1] [--concurrency 1] [--crf 18] [--stills 30,90 --still-dir DIR] [--frames 0-89]
import path from 'node:path';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition, openBrowser} from '@remotion/renderer';

const here = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const arg = (k, d) => {
  const i = argv.indexOf('--' + k);
  return i >= 0 ? argv[i + 1] : d;
};
const propsFile = arg('props');
const browserExecutable = arg('browser') || null;
const outDir = path.resolve(arg('out-dir', 'build'));
const comps = arg('comp', 'DemoH').split(',');
const names = arg('names', '').split(',').filter(Boolean);
const _s = arg('scale', '1'); const scale = _s.includes('/') ? _s.split('/').reduce((a, b) => Number(a) / Number(b)) : parseFloat(_s);
const concurrency = parseInt(arg('concurrency', '1'), 10);
const crf = parseInt(arg('crf', '18'), 10);
const jpegQuality = parseInt(arg('jpeg', '92'), 10);
const colorSpace = arg('colorspace', '');
const stills = arg('stills', '').split(',').filter(Boolean).map(Number);
const stillDir = arg('still-dir', outDir);
const frameRange = arg('frames', '');
const every = parseInt(arg('every', '1'), 10); // benchmark: render every Nth frame only
const inputProps = JSON.parse(fs.readFileSync(propsFile, 'utf8'));
fs.mkdirSync(outDir, {recursive: true});

const t0 = Date.now();
const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s]`, ...a);

const serveUrl = await bundle({
  entryPoint: path.join(here, 'src/index.ts'),
  publicDir: path.join(here, 'public'),
  onProgress: (p) => {
    if (p % 25 === 0) log('bundling', p + '%');
  },
});
log('bundled');

const browser = await openBrowser('chrome', {
  browserExecutable,
  chromiumOptions: {gl: 'swangle', disableWebSecurity: false, ignoreCertificateErrors: false},
  logLevel: 'warn',
});

for (let ci = 0; ci < comps.length; ci++) {
  const id = comps[ci];
  const composition = await selectComposition({serveUrl, id, inputProps, puppeteerInstance: browser, browserExecutable});
  log(id, composition.width + 'x' + composition.height, composition.durationInFrames + ' frames');
  if (stills.length) {
    fs.mkdirSync(stillDir, {recursive: true});
    for (const fr of stills) {
      const out = path.join(stillDir, `${id}_${String(fr).padStart(5, '0')}.png`);
      await renderStill({composition, serveUrl, inputProps, frame: fr, output: out, puppeteerInstance: browser, browserExecutable, imageFormat: 'png', scale});
    }
    log('stills done', id);
    continue;
  }
  const out = path.join(outDir, names[ci] || `${id}.mp4`);
  let lastLog = 0;
  const tRender = Date.now();
  await renderMedia({
    composition,
    serveUrl,
    inputProps,
    outputLocation: out,
    codec: 'h264',
    crf,
    x264Preset: arg('preset', 'fast'),
    pixelFormat: 'yuv420p',
    imageFormat: 'jpeg',
    jpegQuality,
    ...(colorSpace ? {colorSpace} : {}),
    concurrency,
    ...(every > 1 ? {everyNthFrame: every} : {}),
    scale,
    muted: true,
    puppeteerInstance: browser,
    browserExecutable,
    ...(frameRange ? {frameRange: frameRange.includes('-') ? frameRange.split('-').map(Number) : Number(frameRange)} : {}),
    onProgress: ({renderedFrames, encodedFrames}) => {
      const now = Date.now();
      if (now - lastLog > 15000) {
        lastLog = now;
        log(`${id}: rendered ${renderedFrames}/${composition.durationInFrames}, encoded ${encodedFrames}`);
      }
    },
  });
  log('rendered', out, `(render phase ${((Date.now() - tRender) / 1000).toFixed(1)} s)`);
}
await browser.close({silent: true});
log('done');
