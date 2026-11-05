import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import App from './App';
import AuthProvider from './Context/AuthProvider';
import ContextProvider from './Context/ContextProvider';
import { clearToken, getToken, resetGuestId } from './Config/session';

// Only the network is simulated: screens, session API, and providers are real.
let account, messages, agentBody, agentStatus, agentHeaders, verifyBody, profileBodies;
const response = (data, status = 200) => ({
  ok: status < 400, status, statusText: '',
  headers: { get: () => null }, json: async () => data,
});
const mount = () => render(
  <AuthProvider><ContextProvider><App /></ContextProvider></AuthProvider>
);
const SIGNED_IN_ONLY = ['/auth/me', '/history', '/profile', '/auth/signout'];

beforeEach(() => {
  clearToken();
  resetGuestId();
  // What the backend's claim_guest leaves behind: the crop the guest asked
  // about is on the account by the time verify answers.
  account = { user_id: '+919999000099', crops: ['wheat'], onboarded_at: null };
  messages = [];
  agentBody = { answer: 'This is a simulated advisory answer.', tools_used: [] };
  agentStatus = 200;
  agentHeaders = [];
  verifyBody = null;
  profileBodies = [];
  Element.prototype.scrollIntoView = jest.fn();
  global.fetch = jest.fn(async (url, options = {}) => {
    const path = new URL(url).pathname;
    const body = options.body ? JSON.parse(options.body) : {};
    const authorised = options.headers?.Authorization === 'Bearer test-session';
    if (SIGNED_IN_ONLY.includes(path) && !authorised) return response({ detail: 'sign in' }, 401);
    if (path === '/auth/request-code') return response({ transport: 'console', phone: '+91 ***** 00099' });
    if (path === '/auth/verify') {
      verifyBody = body;
      return body.code === '123456'
        ? response({ token: 'test-session', user: account, needs_onboarding: true })
        : response({ detail: 'That code is wrong' }, 401);
    }
    if (path === '/auth/me') return response({ user: account, needs_onboarding: !account.onboarded_at });
    if (path === '/history') return response({ messages });
    if (path === '/agent') {
      agentHeaders.push(options.headers || {});
      if (agentStatus !== 200) return response(agentBody, agentStatus);
      if (agentBody.answer) messages.push({ direction: 'inbound', body: body.query }, { direction: 'outbound', body: agentBody.answer });
      return response(agentBody);
    }
    if (path === '/profile') {
      profileBodies.push(body);
      account = { ...account, ...body, onboarded_at: '2026-11-05T00:00:00Z' };
      return response({ saved: true, user: account });
    }
    if (path === '/auth/signout') return response({ signed_out: true });
    // The sidebar's weather lookups and anything else: not part of this journey.
    return response({}, 404);
  });
});
afterEach(() => { clearToken(); delete global.fetch; });

const composer = () => screen.getByPlaceholderText('Ask about your crop, in any language');
function ask(text = 'Mere gehun me peela rog') {
  fireEvent.change(composer(), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Send', exact: true }));
}
async function confirmNumber(within_ = screen) {
  fireEvent.change(within_.getByPlaceholderText('98765 43210'), { target: { value: '9999000099' } });
  fireEvent.click(within_.getByRole('button', { name: 'Send me a code' }));
  fireEvent.change(await screen.findByLabelText('Enter the code'), { target: { value: '123456' } });
}

test('a guest asks, saves their farm in two steps, reloads, and signs out', async () => {
  const view = mount();
  // The conversation is there at once - no number asked for.
  expect(composer()).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Send me a code' })).not.toBeInTheDocument();

  ask();
  await screen.findByText('This is a simulated advisory answer.');
  // Asked as a guest: a browser id, no token.
  expect(agentHeaders[0]['X-Guest-Id']).toMatch(/^[0-9a-f-]{36}$/);
  expect(agentHeaders[0].Authorization).toBeUndefined();
  const guestId = agentHeaders[0]['X-Guest-Id'];

  fireEvent.click(screen.getByRole('button', { name: 'Add farm details' }));
  const save = screen.getByRole('region', { name: 'Save your farm' });
  await confirmNumber(within(save));
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

  // Step one. The guest id went with the code, so the backend can move the
  // question onto this number.
  await screen.findByRole('region', { name: 'About you' });
  expect(verifyBody).toEqual({ phone: '9999000099', code: '123456', guest_id: guestId });
  expect(getToken()).toBe('test-session');
  fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Test Farmer' } });
  fireEvent.click(screen.getByRole('button', { name: 'Next: your farm' }));

  // Step two, with the crop from the question already marked.
  await screen.findByRole('region', { name: 'Your farm' });
  expect(screen.getByRole('button', { name: 'wheat' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.change(screen.getByLabelText('Your district'), { target: { value: 'Karnal' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save farm details' }));
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Your farm' })).not.toBeInTheDocument());
  expect(profileBodies[0]).toMatchObject({ name: 'Test Farmer' });
  expect(profileBodies[1]).toMatchObject({ district: 'Karnal', crops: ['wheat'] });
  // The answer they came for is still on screen.
  expect(screen.getByText('This is a simulated advisory answer.')).toBeInTheDocument();

  // Now asking as themselves.
  ask('Aur kitna paani dena hai?');
  await waitFor(() => expect(agentHeaders).toHaveLength(2));
  expect(agentHeaders[1].Authorization).toBe('Bearer test-session');
  expect(agentHeaders[1]['X-Guest-Id']).toBeUndefined();

  view.unmount();
  mount();
  await screen.findAllByText('This is a simulated advisory answer.');
  expect(screen.queryByRole('region', { name: 'About you' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Add farm details' })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /sign out/i }));
  await screen.findByRole('button', { name: 'Sign in' });
  expect(getToken()).toBe('');
  expect(screen.queryByText('This is a simulated advisory answer.')).not.toBeInTheDocument();
});

test('a guest at the limit is invited to confirm their number, not shown an error', async () => {
  agentStatus = 429;
  agentBody = { detail: 'You have asked several questions without signing in. Confirm your phone number to keep asking - it takes a minute.' };
  mount();
  ask();
  await screen.findByText(/You have asked several questions without signing in/);
  expect(screen.getByText('Confirm your number to keep asking')).toBeInTheDocument();
  expect(screen.queryByText(/could not reach the AnnaData service/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Not now' })).not.toBeInTheDocument();
});

test('a returning farmer signs in from the header', async () => {
  account = { ...account, onboarded_at: '2026-10-01T00:00:00Z', name: 'Ramesh' };
  messages = [{ direction: 'inbound', body: 'Old question' }, { direction: 'outbound', body: 'Old answer' }];
  mount();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await confirmNumber();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  await screen.findByText('Old answer');
  expect(composer()).toBeInTheDocument();
});

test('an empty API answer does not offer saving', async () => {
  agentBody = {};
  mount();
  ask();
  await screen.findByText(/could not reach the AnnaData service/i);
  expect(screen.queryByRole('button', { name: 'Add farm details' })).not.toBeInTheDocument();
});
