import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import VoiceMode, { wordAtFraction, wordAtChar } from './VoiceMode';
import { Context } from '../../Context/ContextProvider';
import { Flow } from '../../Context/Flow';

jest.mock('../../Config/speech', () => ({
  speak: jest.fn(), stopSpeaking: jest.fn(), unlockAudio: jest.fn(),
  createSpeaker: jest.fn(), speechProgress: jest.fn(() => null), sharedAudioContext: jest.fn(),
}));

function show(onClose = jest.fn()) {
  render(
    <Context.Provider value={{ send: jest.fn() }}>
      <Flow.Provider value={jest.fn()}>
        <VoiceMode onClose={onClose} />
      </Flow.Provider>
    </Context.Provider>
  );
  return onClose;
}

afterEach(() => { delete navigator.mediaDevices; });

test('a refused microphone is explained, not left as a silent orb', async () => {
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: jest.fn().mockRejectedValue(new Error('denied')) },
  });
  show();
  expect(await screen.findByText(/Microphone unavailable/)).toBeInTheDocument();
  expect(screen.getByText('Paused')).toBeInTheDocument();
});

test('End closes voice mode', async () => {
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: jest.fn().mockRejectedValue(new Error('denied')) },
  });
  const onClose = show();
  fireEvent.click(screen.getByRole('button', { name: 'End voice conversation' }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
});

describe('subtitles follow the voice', () => {
  const words = 'Gehu ki buwai November mein karein.'.split(' ');
  test('the start of the audio is the first word', () => {
    expect(wordAtFraction(words, 0)).toBe(0);
  });
  test('the end of the audio is the last word', () => {
    expect(wordAtFraction(words, 1)).toBe(words.length - 1);
  });
  test('halfway is somewhere in the middle, in order', () => {
    const marks = [0.1, 0.3, 0.5, 0.7, 0.9].map((f) => wordAtFraction(words, f));
    expect(marks).toEqual([...marks].sort((a, b) => a - b));
    expect(marks[2]).toBeGreaterThan(0);
    expect(marks[2]).toBeLessThan(words.length - 1);
  });
  test("the phone's voice names the word by its first character", () => {
    const text = 'Gehu ki buwai';
    expect(wordAtChar(text, 0)).toBe(0);
    expect(wordAtChar(text, 5)).toBe(1);
    expect(wordAtChar(text, 8)).toBe(2);
  });
});
