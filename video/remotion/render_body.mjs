import path from 'node:path'; import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler'; import {renderMedia, renderStill, selectComposition, openBrowser} from '@remotion/renderer';
const here = path.dirname(fileURLToPath(import.meta.url)); const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const browserExecutable = arg('browser'); const out = arg('out'); const stills = arg('stills', '').split(',').filter(Boolean).map(Number); const sd = arg('still-dir', 'stills');
const fr = arg('frames', '');
const inputProps = {qr: 'qr.png'};
const serveUrl = await bundle({entryPoint: path.join(here, 'src/index.ts'), publicDir: path.join(here, 'public')});
const browser = await openBrowser('chrome', {browserExecutable, chromiumOptions: process.env.RENDER_GL === 'none' ? {} : {gl: process.env.RENDER_GL || 'swangle'}, logLevel: 'warn'});
const composition = await selectComposition({serveUrl, id: 'KaikuBody', inputProps, puppeteerInstance: browser, browserExecutable});
console.log(composition.durationInFrames, 'frames');
if (stills.length) { for (const f of stills) await renderStill({composition, serveUrl, inputProps, frame: f, output: path.join(sd, `b_${String(f).padStart(5, '0')}.png`), puppeteerInstance: browser, browserExecutable, imageFormat: 'png'}); }
else { let last = 0; await renderMedia({composition, serveUrl, inputProps, outputLocation: out, codec: 'h264', crf: 16, x264Preset: 'fast', pixelFormat: 'yuv420p', imageFormat: 'jpeg', jpegQuality: 92, concurrency: Number(process.env.CONC||1), scale: Number(process.env.RENDER_SCALE||1), timeoutInMilliseconds: 300000, offthreadVideoCacheSizeInBytes: 300 * 1024 * 1024, muted: true, ...(fr ? {frameRange: fr.split('-').map(Number)} : {}), puppeteerInstance: browser, browserExecutable,
  onProgress: ({renderedFrames}) => { if (Date.now() - last > 20000) { last = Date.now(); console.log('rendered', renderedFrames); } }}); }
await browser.close({silent: true});
