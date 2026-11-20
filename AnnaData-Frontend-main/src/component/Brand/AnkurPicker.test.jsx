import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import Ankur, { AnkurButton } from './Ankur';

beforeEach(() => window.localStorage.clear());

test('tapping Ankur opens the picker with the ready looks, and a pick changes Ankur everywhere', () => {
  const { container } = render(<><AnkurButton /><Ankur pose="think" /></>);
  fireEvent.click(screen.getByRole('button', { name: 'Change Ankur' }));
  const dialog = screen.getByRole('dialog', { name: 'Choose your Ankur' });
  const looks = within(dialog).getAllByRole('button', { pressed: false }).concat(within(dialog).getAllByRole('button', { pressed: true }));
  expect(looks).toHaveLength(2);
  expect(dialog).toHaveTextContent(/Master Ankur.*Bengal/);
  expect(within(dialog).queryByText('Punjab')).toBeNull();
  expect(within(dialog).queryByText('Assam')).toBeNull();
  expect(within(dialog).getByRole('button', { pressed: true })).toHaveTextContent('Master Ankur');

  fireEvent.click(within(dialog).getByText('Bengal'));
  expect(screen.queryByRole('dialog')).toBeNull();
  const srcs = [...container.querySelectorAll('img')].map((img) => img.getAttribute('src'));
  expect(srcs).toEqual(['/avatars/ankur-bengal.webp', '/avatars/ankur-bengal-think.webp']);
  expect(window.localStorage.getItem('annadata.avatar')).toBe('bengal');
});

test('the picker closes on Escape without changing Ankur', () => {
  render(<AnkurButton />);
  fireEvent.click(screen.getByRole('button', { name: 'Change Ankur' }));
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(window.localStorage.getItem('annadata.avatar')).toBeNull();
});

test('resting Ankur plays the idle loop where it can, with the still as poster; elsewhere the still', () => {
  const avatarModule = require('../../Config/avatar');
  avatarModule.chooseAvatar('bengal');
  const spy = jest.spyOn(avatarModule, 'canPlayIdle');
  spy.mockReturnValue(true);
  const { container, unmount } = render(<><Ankur /><Ankur pose="think" /></>);
  const video = container.querySelector('video');
  expect(video.getAttribute('src')).toBe('/avatars/ankur-bengal-idle.webm');
  expect(video.getAttribute('poster')).toBe('/avatars/ankur-bengal.webp');
  expect(container.querySelector('img').getAttribute('src')).toBe('/avatars/ankur-bengal-think.webp');
  unmount();
  spy.mockReturnValue(false);
  const again = render(<Ankur />);
  expect(again.container.querySelector('video')).toBeNull();
  expect(again.container.querySelector('img').getAttribute('src')).toBe('/avatars/ankur-bengal.webp');
  spy.mockRestore();
});
