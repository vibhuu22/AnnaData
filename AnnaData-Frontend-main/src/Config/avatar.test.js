import { AVATARS, currentAvatar, chooseAvatar, DEFAULT_AVATAR, pickableAvatars, posesOf } from './avatar';

beforeEach(() => window.localStorage.clear());

test('Master Ankur is the default look', () => {
  expect(DEFAULT_AVATAR).toBe('master');
  expect(currentAvatar().id).toBe('master');
  expect(currentAvatar().src).toMatch(/avatars\/ankur-master\.webp$/);
});

test('a chosen look is remembered on this phone; an unknown or not-yet-posed one falls back to the default', () => {
  chooseAvatar('bengal');
  expect(currentAvatar().region).toBe('Bengal');
  chooseAvatar('nowhere');
  expect(currentAvatar().id).toBe('master');
  chooseAvatar('punjab');
  expect(currentAvatar().id).toBe('master');
});

test('only looks drawn in all six poses can be picked', () => {
  expect(pickableAvatars().map((a) => a.id)).toEqual(['master', 'bengal']);
});

test('all seven regional looks are available', () => {
  expect(AVATARS.map((a) => a.id)).toEqual(['master', 'assam', 'bengal', 'punjab', 'rajasthan', 'maharashtra', 'tamil', 'up']);
});

test('Master Ankur acts in every voice-mode pose; a look without poses has none', () => {
  const poses = posesOf(currentAvatar());
  expect(Object.keys(poses)).toEqual(['hello', 'listen', 'think', 'talk-open', 'talk-half', 'sorry', 'success']);
  expect(poses.listen).toMatch(/avatars\/ankur-master-listen\.webp$/);
  expect(poses['talk-half']).toMatch(/avatars\/ankur-master-talk-half\.webp$/);
  expect(poses['talk-half']).not.toBe(poses['talk-open']);
  expect(posesOf(AVATARS.find((a) => a.id === 'punjab'))).toBeNull();
});

test('Bengal acts in all six poses, and every pose of every look has its picture', () => {
  const fs = require('fs');
  const path = require('path');
  const bengal = posesOf(AVATARS.find((a) => a.id === 'bengal'));
  expect(Object.keys(bengal)).toEqual(['hello', 'listen', 'think', 'talk-open', 'talk-half', 'sorry', 'success']);
  for (const look of AVATARS) {
    for (const src of Object.values(posesOf(look) || { hello: look.src })) {
      const file = path.join(__dirname, '../../public', src.replace(/^.*?\/avatars\//, 'avatars/'));
      expect(fs.existsSync(file)).toBe(true);
    }
  }
});
