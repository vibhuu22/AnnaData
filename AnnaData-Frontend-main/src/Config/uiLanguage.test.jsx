jest.mock('./traffic', () => ({ startTraffic: jest.fn(), trackMessage: jest.fn() }));
import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { initialLanguage, setUiLanguage, t, useUiLanguage } from './uiLanguage';
import LanguageToggle from '../component/Brand/LanguageToggle';

afterEach(() => { act(() => setUiLanguage('en')); localStorage.clear(); });

test('Hindi phones default to Hindi; an explicit preference wins', () => {
  const lang = jest.spyOn(navigator, 'language', 'get').mockReturnValue('hi-IN');
  localStorage.clear();
  expect(initialLanguage()).toBe('hi');
  localStorage.setItem('annadata.uiLanguage', 'en');
  expect(initialLanguage()).toBe('en');
  lang.mockRestore();
});

test('toggle changes labels without remounting form input or translating answers', () => {
  function Screen() {
    useUiLanguage();
    return <><LanguageToggle /><label>{t('Mobile number')}<input defaultValue="9876543210" /></label><p>Gehu ki buwai November mein karein.</p></>;
  }
  render(<Screen />);
  const input = screen.getByRole('textbox');
  fireEvent.click(screen.getByRole('button', { name: 'इंटरफ़ेस हिंदी में बदलें' }));
  expect(screen.getByLabelText('मोबाइल नंबर')).toBe(input);
  expect(input).toHaveValue('9876543210');
  expect(screen.getByText('Gehu ki buwai November mein karein.')).toBeInTheDocument();
  expect(localStorage.getItem('annadata.uiLanguage')).toBe('hi');
  expect(document.documentElement.lang).toBe('hi');
  fireEvent.click(screen.getByRole('button', { name: 'Switch interface to English' }));
  expect(screen.getByLabelText('Mobile number')).toBe(input);
});

test('blocked storage still allows switching during a visit', () => {
  const read = jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
  const write = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
  expect(() => initialLanguage()).not.toThrow();
  setUiLanguage('hi');
  expect(t('Send code')).toBe('कोड भेजें');
  read.mockRestore(); write.mockRestore();
});
