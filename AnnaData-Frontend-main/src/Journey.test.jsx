import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import AuthProvider from './Context/AuthProvider';
import ContextProvider from './Context/ContextProvider';
import { clearToken, getToken } from './Config/session';

// Only the network is simulated: screens, session API, and providers are real.
let account, messages, agentBody;
const response = (data, status = 200) => ({
  ok: status < 400, status, statusText: '',
  headers: { get: () => null }, json: async () => data,
});
const mount = () => render(
  <AuthProvider><ContextProvider><App /></ContextProvider></AuthProvider>
);

beforeEach(() => {
  clearToken();
  account = { user_id: '+919999000099', crops: [], onboarded_at: null };
  messages = [];
  agentBody = { answer: 'This is a simulated advisory answer.', tools_used: [] };
  Element.prototype.scrollIntoView = jest.fn();
  global.fetch = jest.fn(async (url, options = {}) => {
    const path = new URL(url).pathname;
    const body = options.body ? JSON.parse(options.body) : {};
    if (path === '/auth/request-code') return response({ transport: 'console', phone: '+91 ***** 00099' });
    if (path === '/auth/verify') return body.code === '123456'
      ? response({ token: 'test-session', user: account, needs_onboarding: true })
      : response({ detail: 'That code is wrong' }, 401);
    expect(options.headers?.Authorization).toBe('Bearer test-session');
    if (path === '/auth/me') return response({ user: account, needs_onboarding: !account.onboarded_at });
    if (path === '/history') return response({ messages });
    if (path === '/agent') {
      if (agentBody.answer) messages.push({ direction: 'inbound', body: body.query }, { direction: 'outbound', body: agentBody.answer });
      return response(agentBody);
    }
    if (path === '/profile') {
      account = { ...account, ...body, onboarded_at: '2026-11-05T00:00:00Z' };
      return response({ saved: true, user: account });
    }
    if (path === '/auth/signout') return response({ signed_out: true });
    throw new Error(`Unexpected request: ${path}`);
  });
});
afterEach(() => { clearToken(); delete global.fetch; });

async function login() {
  fireEvent.change(screen.getByPlaceholderText('98765 43210'), { target: { value: '9999000099' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send me a code' }));
  fireEvent.change(await screen.findByLabelText('Enter the code'), { target: { value: '123456' } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await screen.findByPlaceholderText('Ask about your crop, in any language');
  await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/history?'), expect.anything()));
}
function ask() {
  fireEvent.change(screen.getByPlaceholderText('Ask about your crop, in any language'), { target: { value: 'Help with my crop' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send', exact: true }));
}

test.each(['Save farm details', 'Skip for now'])('full journey: answer, %s, reload, logout', async (action) => {
  const view = mount();
  await login();
  expect(screen.queryByRole('region', { name: 'Your farm profile' })).not.toBeInTheDocument();
  ask();
  await screen.findByText('This is a simulated advisory answer.');
  expect(screen.getByRole('region', { name: 'Your farm profile' })).toBeInTheDocument();
  if (action === 'Save farm details') fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Test Farmer' } });
  fireEvent.click(screen.getByRole('button', { name: action }));
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Your farm profile' })).not.toBeInTheDocument());
  expect(getToken()).toBe('test-session');
  view.unmount();
  mount();
  await screen.findByText('This is a simulated advisory answer.');
  expect(screen.queryByRole('region', { name: 'Your farm profile' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /sign out/i }));
  await screen.findByRole('button', { name: 'Send me a code' });
  expect(getToken()).toBe('');
  expect(screen.queryByText('This is a simulated advisory answer.')).not.toBeInTheDocument();
});

test('an empty API answer does not trigger profile questions', async () => {
  agentBody = {};
  mount();
  await login();
  ask();
  await screen.findByText(/could not reach the AnnaData service/i);
  expect(screen.queryByRole('region', { name: 'Your farm profile' })).not.toBeInTheDocument();
});
