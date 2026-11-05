import { piecesOf, speakableText } from './speech';

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
