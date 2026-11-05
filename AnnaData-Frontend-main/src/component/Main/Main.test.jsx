import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Main from './Main';
import { Auth } from '../../Context/AuthProvider';
import { Context } from '../../Context/ContextProvider';
import { saveProfile } from '../../Config/session';

jest.mock('../../Config/session', () => ({
  saveProfile: jest.fn(), requestCode: jest.fn(), verifyCode: jest.fn(),
}));
jest.mock('../../Config/speech', () => ({
  speak: jest.fn(), stopSpeaking: jest.fn(), isSpeechSupported: () => false,
}));

const onboarded = jest.fn();
const setUser = jest.fn();
const FARMER = { user_id: 'farmer', crops: ['wheat'] };

function show(responses = [], { user = FARMER, needsOnboarding = true } = {}) {
  return render(
    <Auth.Provider value={{ user, needsOnboarding, onboarded, setUser }}>
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

const NOT_YET = [
  [],
  [{ id: '1', pending: true, response: '' }],
  [{ id: '1', failed: true, response: 'Unavailable' }],
  [{ id: '1', response: '   ' }],
];

describe('a guest', () => {
  test.each(NOT_YET.map((t) => [t]))('is not offered saving before a real answer: %j', (turns) => {
    show(turns, { user: null });
    expect(screen.queryByRole('button', { name: 'Add farm details' })).not.toBeInTheDocument();
  });

  test('is offered saving once, after the newest answer, and can say not now', () => {
    show([{ id: '1', response: 'First' }, { id: '2', response: 'Second' }], { user: null });
    expect(screen.getAllByRole('button', { name: 'Add farm details' })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }));
    expect(screen.queryByRole('button', { name: 'Add farm details' })).not.toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
  });

  test('"Add farm details" opens number confirmation in place', () => {
    show([{ id: '1', response: 'An answer' }], { user: null });
    fireEvent.click(screen.getByRole('button', { name: 'Add farm details' }));
    expect(screen.getByRole('region', { name: 'Save your farm' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('98765 43210')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Not now — keep asking/ }));
    expect(screen.getByRole('button', { name: 'Add farm details' })).toBeInTheDocument();
  });

  test('at the guest limit is shown the way on, not an error, and cannot dismiss it', () => {
    show([{ id: '1', response: 'Confirm your phone number to keep asking.', needsSignIn: true }], { user: null });
    expect(screen.getByText('Confirm your number to keep asking')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Not now' })).not.toBeInTheDocument();
    expect(screen.getByText('Confirm your phone number to keep asking.').closest('.text-red-700')).toBeNull();
  });
});

describe('a farmer who has just confirmed their number', () => {
  test.each(NOT_YET.map((t) => [t]))('is not asked for a profile before a real answer: %j', (turns) => {
    show(turns);
    expect(screen.queryByRole('region', { name: 'About you' })).not.toBeInTheDocument();
  });

  test('goes through About you, then Your farm, with the crop they asked about marked', async () => {
    saveProfile.mockResolvedValue({ user: FARMER });
    show([{ id: '1', response: 'Your first answer' }, { id: '2', response: 'Another answer' }]);
    expect(screen.getAllByRole('region', { name: 'About you' })).toHaveLength(1);
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Ramesh' } });
    fireEvent.click(screen.getByRole('button', { name: 'FPO' }));
    fireEvent.change(screen.getByLabelText('Its name'), { target: { value: 'Kisan Sangh' } });
    fireEvent.click(screen.getByRole('button', { name: 'Next: your farm' }));

    await screen.findByRole('region', { name: 'Your farm' });
    expect(saveProfile).toHaveBeenCalledWith({
      name: 'Ramesh', language: null, farmer_group: 'fpo', farmer_group_name: 'Kisan Sangh',
    });
    // Step one alone does not finish onboarding.
    expect(onboarded).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'wheat' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Save farm details' }));
    await waitFor(() => expect(onboarded).toHaveBeenCalledWith(FARMER));
    expect(saveProfile).toHaveBeenLastCalledWith(expect.objectContaining({ crops: ['wheat'] }));
    expect(screen.getByText('Your first answer')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Ask about your crop, in any language')).toBeInTheDocument();
  });

  test('can skip both steps', async () => {
    saveProfile.mockResolvedValue({ user: FARMER });
    show([{ id: '1', response: 'An answer' }]);
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    await screen.findByRole('region', { name: 'Your farm' });
    expect(saveProfile).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Skip for now' }));
    await waitFor(() => expect(onboarded).toHaveBeenCalledWith(FARMER));
  });

  test('is not asked again once onboarded', () => {
    show([{ id: 'history-1', response: 'Previous answer' }], { needsOnboarding: false });
    expect(screen.queryByRole('region', { name: 'About you' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add farm details' })).not.toBeInTheDocument();
  });
});
