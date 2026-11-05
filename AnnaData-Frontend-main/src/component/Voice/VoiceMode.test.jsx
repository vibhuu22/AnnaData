import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import VoiceMode from './VoiceMode';
import { Context } from '../../Context/ContextProvider';
import { Flow } from '../../Context/Flow';

jest.mock('../../Config/speech', () => ({ speak: jest.fn(), stopSpeaking: jest.fn(), unlockAudio: jest.fn() }));

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
