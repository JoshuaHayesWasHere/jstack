import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readdirSync, readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {getCompositions} from '@remotion/renderer';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sceneIds = Array.from({length: 10}, (_, i) => `Scene${String(i + 1).padStart(2, '0')}`);
const seconds = [4, 6, 5, 5, 5, 6, 8, 9, 7, 5];

const compositions = async () => {
  const serveUrl = await bundle({entryPoint: path.join(root, 'src/index.js')});
  return getCompositions(serveUrl);
};

test('the Film runs as long as its ten scenes together, each at the storyboard seconds', async () => {
  const byId = new Map((await compositions()).map((c) => [c.id, c]));
  const scenes = sceneIds.map((id) => byId.get(id));
  assert.deepEqual(scenes.map((c) => c?.durationInFrames), seconds.map((s) => s * 60));
  const film = byId.get('Film');
  assert.equal(film.durationInFrames, scenes.reduce((sum, c) => sum + c.durationInFrames, 0));
  assert.equal(film.durationInFrames, 3600);
  for (const c of [film, ...scenes]) {
    assert.deepEqual([c.width, c.height, c.fps], [1920, 1080, 60], c.id);
  }
});

test('no scene types a colour or a font of its own: they come from the theme', () => {
  const dir = path.join(root, 'src/scenes');
  const literal = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|fontFamily\s*:\s*['"`]/;
  for (const file of readdirSync(dir)) {
    const text = readFileSync(path.join(dir, file), 'utf8');
    assert.doesNotMatch(text, literal, file);
  }
});
