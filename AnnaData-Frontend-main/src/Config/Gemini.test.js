jest.mock('./traffic', () => ({ startTraffic: jest.fn(), trackMessage: jest.fn() }));
// jsdom does not expose Node's streams; the browser has them natively.
const { ReadableStream: NodeReadableStream } = require('stream/web');
const { TextDecoder: NodeTextDecoder, TextEncoder: NodeTextEncoder } = require('util');
global.ReadableStream = global.ReadableStream || NodeReadableStream;
global.TextDecoder = global.TextDecoder || NodeTextDecoder;
global.TextEncoder = global.TextEncoder || NodeTextEncoder;

import { ask } from './Gemini';

const okResponse = () => ({
  ok: true, status: 200, headers: { get: () => null },
  json: async () => ({ answer: 'ok', missing_slots: ['crop'], needs_location: true }),
});

beforeEach(() => { global.fetch = jest.fn(async () => okResponse()); });
afterEach(() => { delete global.fetch; });

test.each([
  ['audio/mp4', 'voice.m4a'],        // iPhone Safari
  ['audio/webm;codecs=opus', 'voice.webm'], // Chrome
  ['audio/ogg', 'voice.ogg'],        // Firefox
])('a %s recording is uploaded as %s', async (type, name) => {
  await ask({ audio: new Blob(['x'], { type }) });
  const form = fetch.mock.calls[0][1].body;
  expect(form.get('audio').name).toBe(name);
});

test('the follow-up asks come back, as SMS gets them', async () => {
  const result = await ask({ text: 'Kya daalu?' });
  expect(result.missingSlots).toEqual(['crop']);
  expect(result.needsLocation).toBe(true);
});

test('the backend diagnosis reaches the UI unchanged', async () => {
  const diagnosis = { settled: null, candidates: [{ name: 'Late blight' }] };
  fetch.mockResolvedValue({ ok: true, status: 200, headers: { get: () => null },
    json: async () => ({ answer: 'Please send a clearer photo.', diagnosis }) });
  const result = await ask({ text: 'What is this?' });
  expect(result.diagnosis).toEqual(diagnosis);
});

test('a question is not held up waiting for a location prompt', async () => {
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: jest.fn() } });
  Object.defineProperty(navigator, 'permissions', {
    configurable: true, value: { query: jest.fn(async () => ({ state: 'prompt' })) },
  });
  await ask({ text: 'Kya daalu?' });
  expect(navigator.geolocation.getCurrentPosition).not.toHaveBeenCalled();
  expect(JSON.parse(fetch.mock.calls[0][1].body).latitude).toBeUndefined();
  delete navigator.permissions;
  delete navigator.geolocation;
});

const streamable = typeof ReadableStream !== 'undefined' && typeof TextDecoder !== 'undefined';
(streamable ? test : test.skip)('a streamed answer arrives sentence by sentence, then whole', async () => {
  const lines = [
    { type: 'text', text: 'Pehla vakya. ' },
    { type: 'text', text: 'Doosra vakya.' },
    { type: 'done', answer: 'Pehla vakya. Doosra vakya.\n\n**Registered for this pest (CIB&RC):**', tools_used: ['doses'], dose_status: 'available' },
  ].map((e) => JSON.stringify(e) + '\n').join('');
  const bytes = new TextEncoder().encode(lines);
  global.fetch = jest.fn(async () => ({
    ok: true, status: 200, headers: { get: () => null },
    body: new ReadableStream({ start(c) { c.enqueue(bytes.slice(0, 20)); c.enqueue(bytes.slice(20)); c.close(); } }),
  }));
  const pieces = [];
  const result = await ask({ text: 'q', onText: (p) => pieces.push(p) });
  expect(fetch.mock.calls[0][0]).toMatch(/\/agent\/stream$/);
  expect(pieces).toEqual(['Pehla vakya. ', 'Doosra vakya.']);
  expect(result.answer).toMatch(/Registered for this pest/);
  expect(result.doseStatus).toBe('available');
});

(streamable ? test : test.skip)('a backend without streaming is asked the ordinary way', async () => {
  global.fetch = jest.fn(async (url) => (url.endsWith('/stream')
    ? { ok: false, status: 404, headers: { get: () => null }, json: async () => ({}) }
    : okResponse()));
  const result = await ask({ text: 'q', onText: () => {} });
  expect(fetch.mock.calls.map((c) => c[0].split('/').pop())).toEqual(['stream', 'agent']);
  expect(result.answer).toBe('ok');
});
