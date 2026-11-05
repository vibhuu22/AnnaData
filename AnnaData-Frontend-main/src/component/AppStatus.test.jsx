import { act, fireEvent, render, screen } from '@testing-library/react';
import AppStatus from './AppStatus';

test('connection loss is announced and recovery removes the notice', () => {
  render(<AppStatus />);
  act(() => window.dispatchEvent(new Event('offline')));
  expect(screen.getByRole('status')).toHaveTextContent('Reconnect');
  act(() => window.dispatchEvent(new Event('online')));
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

test('install action only appears when the browser provides a prompt', () => {
  render(<AppStatus />);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  const event = new Event('beforeinstallprompt', { cancelable: true });
  event.prompt = jest.fn().mockResolvedValue(undefined);
  act(() => window.dispatchEvent(event));
  fireEvent.click(screen.getByRole('button', { name: /Add AnnaData/ }));
  expect(event.prompt).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
