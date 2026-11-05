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
