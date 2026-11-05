import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import { Auth } from './Context/AuthProvider';
import { requestCode, verifyCode } from './Config/session';

jest.mock('./Config/session', () => ({ requestCode: jest.fn(), verifyCode: jest.fn() }));
jest.mock('./component/Main/Main', () => () => <div>Farmer conversation</div>);
jest.mock('./component/Sidebar/Sidebar', () => () => null);
// The real header needs nothing from the network, but a stub keeps this file
// about routing: one button, wired to the same prop.
jest.mock('./component/Header/Header', () => ({ onSignIn }) => (
  <button type="button" onClick={onSignIn}>Sign in</button>
));

function show(auth = {}) {
  return render(<Auth.Provider value={{ user: null, checking: false, ...auth }}><App /></Auth.Provider>);
}

beforeEach(() => jest.clearAllMocks());

test('a farmer who has not signed in reaches the conversation straight away', () => {
  show();
  expect(screen.getByText('Farmer conversation')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Send me a code' })).not.toBeInTheDocument();
});

test('the header opens sign-in for a returning farmer, and they can go back', () => {
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(screen.getByRole('button', { name: 'Send me a code' })).toBeDisabled();
  expect(screen.queryByText('Farmer conversation')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to asking' }));
  expect(screen.getByText('Farmer conversation')).toBeInTheDocument();
});

test('OTP journey passes the verified account to authentication', async () => {
  const signedIn = jest.fn();
  const account = { token: 'test-token', user: { user_id: '+919999000099' } };
  requestCode.mockResolvedValue({ phone: '+91 ***** 00099', transport: 'android-gateway' });
  verifyCode.mockResolvedValue(account);
  show({ signedIn });
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  fireEvent.change(screen.getByPlaceholderText('98765 43210'), { target: { value: '9999000099' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send me a code' }));
  fireEvent.change(await screen.findByLabelText('Enter the code'), { target: { value: '123456' } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await waitFor(() => expect(signedIn).toHaveBeenCalledWith(account));
  expect(requestCode).toHaveBeenCalledWith('9999000099');
  expect(verifyCode).toHaveBeenCalledWith('9999000099', '123456');
});

test('failed OTP delivery keeps the farmer on the phone screen', async () => {
  requestCode.mockRejectedValue(new Error('Gateway unavailable'));
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  fireEvent.change(screen.getByPlaceholderText('98765 43210'), { target: { value: '9999000099' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send me a code' }));
  expect(await screen.findByText('Gateway unavailable')).toBeInTheDocument();
  expect(screen.queryByLabelText('Enter the code')).not.toBeInTheDocument();
});

test('signed-in farmers see the conversation, profile or not', () => {
  show({ user: { user_id: '+919999000099' }, needsOnboarding: false });
  expect(screen.getByText('Farmer conversation')).toBeInTheDocument();
});

test('session verification does not expose a conversation prematurely', () => {
  show({ checking: true });
  expect(screen.queryByText('Farmer conversation')).not.toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
