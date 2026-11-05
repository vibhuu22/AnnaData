import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import { Auth } from './Context/AuthProvider';
import { requestCode, verifyCode } from './Config/session';

jest.mock('./Config/session', () => ({ requestCode: jest.fn(), verifyCode: jest.fn(), saveProfile: jest.fn() }));
jest.mock('./component/Main/Main', () => () => <div>Farmer conversation</div>);
jest.mock('./component/Sidebar/Sidebar', () => () => null);
// A stub keeps this file about routing: one button, wired to the same prop.
jest.mock('./component/Header/Header', () => ({ onSignIn }) => (
  <button type="button" onClick={onSignIn}>Sign in</button>
));

function show(auth = {}) {
  return render(
    <Auth.Provider value={{ user: null, checking: false, signedIn: jest.fn(), ...auth }}>
      <App />
    </Auth.Provider>
  );
}
const conversationVisible = () => !screen.getByText('Farmer conversation').closest('.hidden');

beforeEach(() => jest.clearAllMocks());

async function enterNumberAndCode() {
  fireEvent.change(screen.getByPlaceholderText('98765 43210'), { target: { value: '9999000099' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send code' }));
  fireEvent.change(await screen.findByLabelText('6-digit code'), { target: { value: '123456' } });
}

test('a farmer who has not signed in reaches the conversation straight away', () => {
  show();
  expect(conversationVisible()).toBe(true);
  expect(screen.queryByRole('button', { name: 'Send code' })).not.toBeInTheDocument();
});

test('the header opens sign-in full screen, and Back returns to the conversation', () => {
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(screen.getByRole('button', { name: 'Send code' })).toBeDisabled();
  // Hidden behind the step, not thrown away.
  expect(conversationVisible()).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Back' }));
  expect(conversationVisible()).toBe(true);
});

test('a returning farmer signs in and goes straight back to the conversation', async () => {
  const signedIn = jest.fn();
  const account = { token: 'test-token', user: { user_id: '+919999000099' }, needs_onboarding: false };
  requestCode.mockResolvedValue({ phone: '+91 ***** 00099', transport: 'android-gateway' });
  verifyCode.mockResolvedValue(account);
  show({ signedIn });
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await enterNumberAndCode();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await waitFor(() => expect(signedIn).toHaveBeenCalledWith(account));
  expect(requestCode).toHaveBeenCalledWith('9999000099');
  expect(verifyCode).toHaveBeenCalledWith('9999000099', '123456');
  await waitFor(() => expect(conversationVisible()).toBe(true));
});

test('a farmer with no profile yet is taken on to About you after signing in', async () => {
  requestCode.mockResolvedValue({ transport: 'android-gateway' });
  verifyCode.mockResolvedValue({ token: 't', user: { user_id: '+919999000099' }, needs_onboarding: true });
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await enterNumberAndCode();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(await screen.findByRole('heading', { name: 'About you' })).toBeInTheDocument();
});

test('failed code delivery keeps the farmer on the number screen', async () => {
  requestCode.mockRejectedValue(new Error('Gateway unavailable'));
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  fireEvent.change(screen.getByPlaceholderText('98765 43210'), { target: { value: '9999000099' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send code' }));
  expect(await screen.findByText('Gateway unavailable')).toBeInTheDocument();
  expect(screen.queryByLabelText('6-digit code')).not.toBeInTheDocument();
});

test('"Code not arriving?" names the likely reason and offers another number', async () => {
  requestCode.mockResolvedValue({ transport: 'android-gateway' });
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await enterNumberAndCode();
  fireEvent.click(screen.getByRole('button', { name: 'Code not arriving?' }));
  expect(screen.getByText('Our sending phone may be offline')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Use a different number' }));
  expect(screen.getByPlaceholderText('98765 43210')).toBeInTheDocument();
});

test('session verification does not expose a conversation prematurely', () => {
  show({ checking: true });
  expect(screen.queryByText('Farmer conversation')).not.toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
