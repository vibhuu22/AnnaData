import { render, screen, fireEvent } from '@testing-library/react';
import News from './News';
import { Auth } from '../../Context/AuthProvider';
import { fetchNews } from '../../Config/session';

import { getCoordinates } from '../../Config/Gemini';
import { speak, stopSpeaking } from '../../Config/speech';

jest.mock('../../Config/speech', () => ({ speak: jest.fn(), stopSpeaking: jest.fn(), unlockAudio: jest.fn() }));

jest.mock('../../Config/session', () => ({ fetchNews: jest.fn() }));
jest.mock('../../Config/Gemini', () => ({ getCoordinates: jest.fn(() => Promise.resolve(null)) }));

test('Listen speaks the real headline in its language; Stop and leaving cancel playback', async () => {
  getCoordinates.mockResolvedValue(null);
  fetchNews.mockResolvedValue({ place: 'India', items: [
    { title: 'किसानों के लिए समाचार', lang: 'hi', source: 'Publisher', link: 'https://example.org/listen' },
  ] });
  speak.mockImplementation(() => new Promise(() => {}));
  const view = render(<Auth.Provider value={{ user: null }}><News /></Auth.Provider>);
  fireEvent.click(await screen.findByRole('button', { name: 'Listen: किसानों के लिए समाचार' }));
  expect(speak).toHaveBeenCalledWith('किसानों के लिए समाचार', 'hi-IN');
  fireEvent.click(screen.getByRole('button', { name: 'Stop: किसानों के लिए समाचार' }));
  expect(screen.getByRole('button', { name: 'Listen: किसानों के लिए समाचार' })).toBeInTheDocument();
  const calls = stopSpeaking.mock.calls.length;
  view.unmount();
  expect(stopSpeaking.mock.calls.length).toBe(calls + 1);
});

test("headlines for the farmer's state, opening the publisher, marked as unchecked", async () => {
  fetchNews.mockResolvedValue({ place: 'Haryana', items: [
    { title: 'Basmati ke record bhav', source: 'Jagran', link: 'https://example.org/a', published: new Date().toISOString() },
  ] });
  render(<Auth.Provider value={{ user: { state: 'Haryana' } }}><News /></Auth.Provider>);
  const link = await screen.findByRole('link', { name: /Basmati ke record bhav/ });
  expect(fetchNews).toHaveBeenCalledWith('Haryana');
  expect(screen.getByRole('combobox')).toHaveValue('Haryana');
  expect(link).toHaveAttribute('href', 'https://example.org/a');
  expect(link).toHaveAttribute('target', '_blank');
  expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  expect(screen.getByText(/AnnaData does not check them/)).toBeInTheDocument();
});

test('a failure says so, rather than showing an empty page', async () => {
  fetchNews.mockRejectedValue(new Error('down'));
  render(<Auth.Provider value={{ user: null }}><News /></Auth.Provider>);
  expect(await screen.findByText(/News could not be loaded/)).toBeInTheDocument();
});

test('the state the phone is in, when location is allowed, over the profile\'s', async () => {
  getCoordinates.mockResolvedValueOnce({ latitude: 22.34, longitude: 87.3 });
  fetchNews.mockResolvedValue({ place: 'West Bengal', state: 'West Bengal', from: 'location', items: [
    { title: 'Aloo ke bhav', source: 'Anandabazar', link: 'https://example.org/b', published: new Date().toISOString() },
  ] });
  render(<Auth.Provider value={{ user: { state: 'Haryana' } }}><News /></Auth.Provider>);
  await screen.findByRole('link', { name: /Aloo ke bhav/ });
  expect(fetchNews).toHaveBeenCalledWith('Haryana', { latitude: 22.34, longitude: 87.3 });
  expect(screen.getByRole('combobox')).toHaveValue('West Bengal');
  expect(screen.getByText(/in West Bengal/)).toHaveTextContent('where you are now');
});

test('when every news source failed, it says so instead of "no news"', async () => {
  getCoordinates.mockResolvedValue(null);
  fetchNews.mockResolvedValue({ place: 'India', state: '', from: null, items: [], unavailable: true });
  render(<Auth.Provider value={{ user: null }}><News /></Auth.Provider>);
  await screen.findByText(/could not be fetched right now/);
  expect(screen.queryByText(/No farming news found/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
});

test('earlier headlines shown because the sources failed are marked as earlier', async () => {
  getCoordinates.mockResolvedValue(null);
  fetchNews.mockResolvedValue({
    place: 'India', state: '', from: null, stale: true, cached: true,
    items: [{ title: 'Aloo ke bhav gire', link: 'https://e.example/1', source: 'E', published: '2026-11-10T00:00:00+00:00', lang: 'hi' }],
  });
  render(<Auth.Provider value={{ user: null }}><News /></Auth.Provider>);
  await screen.findByRole('link', { name: /Aloo ke bhav/ });
  expect(screen.getByText(/Showing earlier headlines/)).toBeInTheDocument();
});

test('a state picked from the list replaces the location\'s', async () => {
  getCoordinates.mockResolvedValue({ latitude: 22.34, longitude: 87.3 });
  fetchNews.mockResolvedValue({ place: 'West Bengal', state: 'West Bengal', from: 'location', items: [] });
  render(<Auth.Provider value={{ user: null }}><News /></Auth.Provider>);
  await screen.findByText(/No farming news found/);
  fetchNews.mockResolvedValue({ place: 'Punjab', state: 'Punjab', from: 'chosen', items: [] });
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Punjab' } });
  await screen.findByText(/in Punjab/);
  expect(fetchNews).toHaveBeenLastCalledWith('Punjab');
  expect(screen.getByRole('combobox')).toHaveValue('Punjab');
});
