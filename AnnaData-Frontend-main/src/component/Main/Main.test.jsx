import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Main from './Main';
import { Auth } from '../../Context/AuthProvider';
import { Context } from '../../Context/ContextProvider';
import { saveProfile } from '../../Config/session';

jest.mock('../../Config/session', () => ({ saveProfile: jest.fn() }));
jest.mock('../../Config/speech', () => ({
  speak: jest.fn(), stopSpeaking: jest.fn(), isSpeechSupported: () => false,
}));

const onboarded = jest.fn();
function show(responses = [], needsOnboarding = true) {
  return render(
    <Auth.Provider value={{ user: { user_id: 'farmer' }, needsOnboarding, onboarded }}>
      <Context.Provider value={{ responses, input: '', dataSent: responses.length > 0, send: jest.fn() }}>
        <Main />
      </Context.Provider>
    </Auth.Provider>
  );
}
beforeEach(() => {
  jest.clearAllMocks();
  Element.prototype.scrollIntoView = jest.fn();
});

test.each([
  [],
  [{ id: '1', pending: true, response: '' }],
  [{ id: '1', failed: true, response: 'Unavailable' }],
  [{ id: '1', response: '   ' }],
].map(turns => [turns]))('does not ask for a profile before a successful answer: %j', (turns) => {
  show(turns);
  expect(screen.queryByRole('region', { name: 'Your farm profile' })).not.toBeInTheDocument();
});

test.each([false, true])('profile save/skip after an answer preserves chat (skip=%s)', async (skip) => {
  saveProfile.mockResolvedValue({ user: { user_id: 'farmer' } });
  show([{ id: '1', response: 'Your first answer' }, { id: '2', response: 'Another answer' }]);
  expect(screen.getAllByRole('region', { name: 'Your farm profile' })).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: skip ? 'Skip for now' : 'Save farm details' }));
  await waitFor(() => expect(onboarded).toHaveBeenCalledWith({ user_id: 'farmer' }));
  expect(screen.getByText('Your first answer')).toBeInTheDocument();
  expect(screen.getByPlaceholderText('Ask about your crop, in any language')).toBeInTheDocument();
});

test('completed profiles are not prompted again when history loads', () => {
  show([{ id: 'history-1', response: 'Previous answer' }], false);
  expect(screen.queryByRole('region', { name: 'Your farm profile' })).not.toBeInTheDocument();
});
