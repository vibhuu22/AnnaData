import { AVATARS, currentAvatar, chooseAvatar, DEFAULT_AVATAR, posesOf } from './avatar';

beforeEach(() => window.localStorage.clear());

test('Master Ankur is the default look', () => {
  expect(DEFAULT_AVATAR).toBe('master');
  expect(currentAvatar().id).toBe('master');
  expect(currentAvatar().src).toMatch(/avatars\/ankur-master\.webp$/);
});

test('a chosen look is remembered on this phone, and an unknown one falls back to the default', () => {
  chooseAvatar('punjab');
  expect(currentAvatar().region).toBe('Punjab');
  chooseAvatar('nowhere');
  expect(currentAvatar().id).toBe('master');
});

test('all seven regional looks are available', () => {
  expect(AVATARS.map((a) => a.id)).toEqual(['master', 'assam', 'bengal', 'punjab', 'rajasthan', 'maharashtra', 'tamil', 'up']);
});

test('Master Ankur acts in every voice-mode pose; a look without poses has none', () => {
  const poses = posesOf(currentAvatar());
  expect(Object.keys(poses)).toEqual(['hello', 'listen', 'think', 'talk-open', 'talk-half', 'sorry', 'success']);
  expect(poses.listen).toMatch(/avatars\/ankur-master-listen\.webp$/);
  expect(poses['talk-half']).toBe(poses['talk-open']); // no body flicker between unmatched sheet renders
  expect(posesOf(AVATARS.find((a) => a.id === 'punjab'))).toBeNull();
});
