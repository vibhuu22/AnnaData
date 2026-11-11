import { AVATARS, currentAvatar, chooseAvatar, DEFAULT_AVATAR } from './avatar';

beforeEach(() => window.localStorage.clear());

test('Assam is the default look', () => {
  expect(DEFAULT_AVATAR).toBe('assam');
  expect(currentAvatar().id).toBe('assam');
  expect(currentAvatar().src).toMatch(/avatars\/ankur-assam\.webp$/);
});

test('a chosen look is remembered on this phone, and an unknown one falls back to the default', () => {
  chooseAvatar('punjab');
  expect(currentAvatar().region).toBe('Punjab');
  chooseAvatar('nowhere');
  expect(currentAvatar().id).toBe('assam');
});

test('all seven regional looks are available', () => {
  expect(AVATARS.map((a) => a.id)).toEqual(['assam', 'bengal', 'punjab', 'rajasthan', 'maharashtra', 'tamil', 'up']);
});
