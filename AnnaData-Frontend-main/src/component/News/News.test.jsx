import { render, screen } from '@testing-library/react';
import News from './News';
import { Auth } from '../../Context/AuthProvider';
import { fetchNews } from '../../Config/session';

jest.mock('../../Config/session', () => ({ fetchNews: jest.fn() }));

test("headlines for the farmer's state, opening the publisher, marked as unchecked", async () => {
  fetchNews.mockResolvedValue({ place: 'Haryana', items: [
    { title: 'Basmati ke record bhav', source: 'Jagran', link: 'https://example.org/a', published: new Date().toISOString() },
  ] });
  render(<Auth.Provider value={{ user: { state: 'Haryana' } }}><News /></Auth.Provider>);
  const link = await screen.findByRole('link', { name: /Basmati ke record bhav/ });
  expect(fetchNews).toHaveBeenCalledWith('Haryana');
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
