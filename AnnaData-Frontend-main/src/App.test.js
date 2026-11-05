import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import { Auth } from './Context/AuthProvider';
import { requestCode, verifyCode } from './Config/session';

jest.mock('./Config/session', () => ({ requestCode: jest.fn(), verifyCode: jest.fn() }));
jest.mock('./component/Main/Main', () => () => <div>Farmer conversation</div>);
jest.mock('./component/Sidebar/Sidebar', () => () => null);
jest.mock('./component/Header/Header', () => () => null);

function show(auth = {}) {
  return render(<Auth.Provider value={{ user: null, checking: false, ...auth }}><App /></Auth.Provider>);
}

beforeEach(() => jest.clearAllMocks());

test('signed-out farmers must sign in before seeing their conversation', () => {
  show();
  expect(screen.getByRole('button', { name: 'Send me a code' })).toBeDisabled();
  expect(screen.queryByText('Farmer conversation')).not.toBeInTheDocument();
});

test('OTP journey passes the verified account to authentication', async () => {
  const signedIn = jest.fn();
  const account = { token: 'test-token', user: { user_id: '+919999000099' } };
  requestCode.mockResolvedValue({ phone: '+91 ***** 00099', transport: 'android-gateway' });
  verifyCode.mockResolvedValue(account);
  show({ signedIn });
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
  fireEvent.change(screen.getByPlaceholderText('98765 43210'), { target: { value: '9999000099' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send me a code' }));
  expect(await screen.findByText('Gateway unavailable')).toBeInTheDocument();
  expect(screen.queryByLabelText('Enter the code')).not.toBeInTheDocument();
});

test('onboarded farmers can see the conversation', () => {
  show({ user: { user_id: '+919999000099' }, needsOnboarding: false });
  expect(screen.getByText('Farmer conversation')).toBeInTheDocument();
});

test('new farmers reach chat before completing their profile', () => {
  show({ user: { user_id: '+919999000099' }, needsOnboarding: true });
  expect(screen.getByText('Farmer conversation')).toBeInTheDocument();
  expect(screen.queryByText('Tell us about your farm')).not.toBeInTheDocument();
});

test('session verification does not expose a conversation prematurely', () => {
  show({ checking: true });
  expect(screen.queryByText('Farmer conversation')).not.toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
