import { render, screen, fireEvent } from '@testing-library/react';
import News from './News';
import { Auth } from '../../Context/AuthProvider';
import { fetchNews } from '../../Config/session';

import { getCoordinates } from '../../Config/Gemini';

jest.mock('../../Config/session', () => ({ fetchNews: jest.fn() }));
jest.mock('../../Config/Gemini', () => ({ getCoordinates: jest.fn(() => Promise.resolve(null)) }));

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
