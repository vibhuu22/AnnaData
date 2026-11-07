import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SignIn from './SignIn';
import { Auth } from '../../Context/AuthProvider';
import * as session from '../../Config/session';
import * as msg91 from '../../Config/msg91';

jest.mock('../../Config/session', () => ({
  requestCode: jest.fn(() => Promise.resolve({ sent: true, transport: 'gateway' })),
  verifyCode: jest.fn(() => Promise.resolve({ token: 't', user: {} })),
  verifyWidgetToken: jest.fn(() => Promise.resolve({ token: 't', user: {} })),
}));
jest.mock('../../Config/msg91', () => ({
  msg91Enabled: jest.fn(() => false),
  loadWidget: jest.fn(() => Promise.resolve()),
  sendCode: jest.fn(() => Promise.resolve({ type: 'success' })),
  resendCode: jest.fn(() => Promise.resolve({})),
  verifyCode: jest.fn(() => Promise.resolve('msg91-access-token')),
  CAPTCHA_ID: 'msg91-captcha',
  CODE_LENGTH: 6,
}));

const signedIn = jest.fn();
const show = () => render(<Auth.Provider value={{ signedIn }}><SignIn onVerified={jest.fn()} /></Auth.Provider>);

async function signInWith(number, code) {
  fireEvent.change(screen.getByLabelText('Mobile number'), { target: { value: number } });
  fireEvent.click(screen.getByRole('button', { name: 'Send code' }));
  const box = await screen.findByLabelText('6-digit code');
  fireEvent.change(box, { target: { value: code } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await waitFor(() => expect(signedIn).toHaveBeenCalled());
}

beforeEach(() => {
  // CRA resets mock implementations before each test, so they are set here.
  session.requestCode.mockResolvedValue({ sent: true, transport: 'gateway' });
  session.verifyCode.mockResolvedValue({ token: 't', user: {} });
  session.verifyWidgetToken.mockResolvedValue({ token: 't', user: {} });
  msg91.msg91Enabled.mockReturnValue(false);
  msg91.loadWidget.mockResolvedValue();
  msg91.sendCode.mockResolvedValue({ type: 'success' });
  msg91.resendCode.mockResolvedValue({});
  msg91.verifyCode.mockResolvedValue('msg91-access-token');
});

test("without MSG91, AnnaData's own codes are used, as before", async () => {
  show();
  await signInWith('98765 43210', '123456');
  expect(session.requestCode).toHaveBeenCalledWith('9876543210');
  expect(session.verifyCode).toHaveBeenCalledWith('9876543210', '123456');
  expect(msg91.sendCode).not.toHaveBeenCalled();
});

test("with MSG91, its widget sends and checks the code, and the backend confirms MSG91's token", async () => {
  msg91.msg91Enabled.mockReturnValue(true);
  show();
  expect(document.getElementById('msg91-captcha')).not.toBeNull();
  await signInWith('98765 43210', '123456');
  expect(msg91.sendCode).toHaveBeenCalledWith('9876543210');
  expect(msg91.verifyCode).toHaveBeenCalledWith('123456');
  expect(session.verifyWidgetToken).toHaveBeenCalledWith('msg91-access-token');
  expect(session.requestCode).not.toHaveBeenCalled();
});

test("if MSG91's script cannot load, sign-in falls back to AnnaData's own codes", async () => {
  msg91.msg91Enabled.mockReturnValue(true);
  msg91.loadWidget.mockRejectedValue(new Error('blocked'));
  show();
  await waitFor(() => expect(document.getElementById('msg91-captcha')).toBeNull());
  await signInWith('98765 43210', '123456');
  expect(session.requestCode).toHaveBeenCalled();
  expect(msg91.sendCode).not.toHaveBeenCalled();
});
