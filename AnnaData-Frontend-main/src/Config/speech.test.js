import { piecesOf, speakableText, speechLevel, gainFor } from './speech';

test('the first piece is short, so speech starts quickly', () => {
  const text = 'Gehu ki buwai 1 se 25 November ke beech karein. HD 2967 achhi kism hai. ' +
    'Beej ki matra 100 kilo prati hectare rakhein. Buwai se pehle khet ki achhi taiyari karein.';
  const pieces = piecesOf(text, 60, 200);
  expect(pieces[0]).toBe('Gehu ki buwai 1 se 25 November ke beech karein.');
  expect(pieces.join(' ')).toBe(text);
});

test('a dose like 0.5 ml is never split at its decimal point', () => {
  const pieces = piecesOf('Dava 0.5 ml prati litre paani mein milayein. Spray subah karein.', 20, 200);
  expect(pieces.some((p) => p.includes('0.5 ml'))).toBe(true);
});

test('Hindi sentence ends (।) are sentence ends', () => {
  const pieces = piecesOf('गेहूं में पीला रतुआ है। प्रोपिकोनाज़ोल का छिड़काव करें।', 30, 200);
  expect(pieces[0]).toBe('गेहूं में पीला रतुआ है।');
});

test('a sentence longer than a piece is cut at a space, not mid-word', () => {
  const pieces = piecesOf('ek do teen char paanch chhe saat aath nau das gyarah barah', 20, 20);
  pieces.forEach((p) => expect(p.length).toBeLessThanOrEqual(20));
  expect(pieces.join(' ')).toBe('ek do teen char paanch chhe saat aath nau das gyarah barah');
});

test('markdown is not read out', () => {
  expect(speakableText('### Upchar\n*   **Acephate 75% SP:** 780 g/ha')).toBe('Upchar. Acephate 75% SP: 780 g/ha');
});

describe('every piece is played at one loudness', () => {
  const tone = (amplitude, n = 6000, pauseEvery = 0) =>
    Float32Array.from({ length: n }, (_, i) =>
      pauseEvery && Math.floor(i / pauseEvery) % 2 ? 0 : amplitude * Math.sin(i / 3));

  test('a quiet piece is turned up and a loud one down, to the same level', () => {
    const quiet = speechLevel(tone(0.05));
    const loud = speechLevel(tone(0.4));
    expect(quiet * gainFor(quiet)).toBeCloseTo(loud * gainFor(loud), 5);
  });

  test('pauses do not count as quiet speech', () => {
    expect(speechLevel(tone(0.2, 6000, 500))).toBeCloseTo(speechLevel(tone(0.2)), 2);
  });

  test('silence is not measured, so it is never turned up', () => {
    expect(speechLevel(new Float32Array(6000))).toBeNull();
    expect(gainFor(null)).toBeNull();
  });

  test('the gain stays within bounds, so a near-silent piece is not blown up', () => {
    expect(gainFor(0.001)).toBe(6);
    expect(gainFor(0.99)).toBe(0.5);
  });
});
