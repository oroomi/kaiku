import fs from 'node:fs'; import {execSync} from 'node:child_process';
execSync('npx esbuild src/scenes.ts --format=esm --outfile=/tmp/claude-0/scenes_tmp.mjs --log-level=error', {cwd: new URL('.', import.meta.url).pathname});
const m = await import('/tmp/claude-0/scenes_tmp.mjs'); fs.writeFileSync('/root/hack/kaiku/video/build/scenes.json', JSON.stringify(m.SCENES, null, 1)); console.log(m.BODY_FRAMES);
