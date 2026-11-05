import { render, screen, fireEvent } from '@testing-library/react';
import Main from './Main';
import { Auth } from '../../Context/AuthProvider';
import { Context } from '../../Context/ContextProvider';
import { Flow } from '../../Context/Flow';

jest.mock('../../Config/session', () => ({ saveProfile: jest.fn() }));
jest.mock('../../Config/speech', () => ({
  speak: jest.fn(), stopSpeaking: jest.fn(), isSpeechSupported: () => false,
}));

const openFlow = jest.fn();
const send = jest.fn();
const startNewQuestion = jest.fn();
const openTurn = jest.fn();

function show(thread = [], { user = null, needsOnboarding = false, screen: at } = {}) {
  const view = at || (thread.length ? 'chat' : 'ask');
  return render(
    <Auth.Provider value={{ user, needsOnboarding }}>
      <Context.Provider value={{
        thread, responses: thread, screen: view, input: '', setInput: jest.fn(),
        send, startNewQuestion, openTurn, focusId: null, loading: false,
      }}>
        <Flow.Provider value={openFlow}>
          <Main />
        </Flow.Provider>
      </Context.Provider>
    </Auth.Provider>
  );
}
beforeEach(() => {
  jest.clearAllMocks();
  Element.prototype.scrollIntoView = jest.fn();
});

describe('the ask screen', () => {
  test('asks what is happening in the field, with examples that send', () => {
    show();
    expect(screen.getByRole('heading', { name: 'What is happening in your field?' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Gehu ki buwai kab karein?' }));
    expect(send).toHaveBeenCalledWith({ text: 'Gehu ki buwai kab karein?' });
  });

  test('says so, and sends nothing, when there is no connection', () => {
    const spy = jest.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
    show();
    fireEvent.click(screen.getByRole('button', { name: 'Gehu ki buwai kab karein?' }));
    expect(send).not.toHaveBeenCalled();
    expect(screen.getByText('No internet connection')).toBeInTheDocument();
    spy.mockRestore();
  });
});

describe('what kind of answer it is', () => {
  test.each([
    ['available', null, 'Approved dose'],
    ['none_registered', null, 'No approved spray for this'],
    [null, { crop: 'tomato', pest: 'unknown', stage: 'unknown', severity: 'unknown', confidence: 'low' }, 'Photo is not enough to be sure'],
  ])('dose_status %s / photo %j is badged "%s"', (doseStatus, vision, badge) => {
    show([{ id: '1', prompt: 'q', response: 'An answer', doseStatus, vision }]);
    expect(screen.getByText(badge)).toBeInTheDocument();
  });

  test('an ordinary answer carries no badge', () => {
    show([{ id: '1', prompt: 'q', response: 'An answer', doseStatus: 'not_applicable' }]);
    ['Approved dose', 'No approved spray for this', 'Photo is not enough to be sure']
      .forEach((badge) => expect(screen.queryByText(badge)).not.toBeInTheDocument());
  });

  test('a pending answer says it is looking it up', () => {
    show([{ id: '1', prompt: 'q', response: '', pending: true, startedAt: Date.now() }]);
    expect(screen.getByText('Looking this up for you…')).toBeInTheDocument();
  });
});

const NOT_YET = [
  [{ id: '1', pending: true, response: '' }],
  [{ id: '1', failed: true, response: 'Unavailable' }],
  [{ id: '1', response: '   ' }],
];

describe('a guest', () => {
  test.each(NOT_YET.map((t) => [t]))('is not offered saving before a real answer: %j', (turns) => {
    show(turns);
    expect(screen.queryByRole('button', { name: 'Add farm details' })).not.toBeInTheDocument();
  });

  test('is offered saving once, after the newest answer, and can say not now', () => {
    show([{ id: '1', response: 'First' }, { id: '2', response: 'Second' }]);
    expect(screen.getAllByRole('button', { name: 'Add farm details' })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }));
    expect(screen.queryByRole('button', { name: 'Add farm details' })).not.toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
  });

  test('"Add farm details" opens the save steps', () => {
    show([{ id: '1', response: 'An answer' }]);
    fireEvent.click(screen.getByRole('button', { name: 'Add farm details' }));
    expect(openFlow).toHaveBeenCalledWith('save');
  });

  test('at the guest limit is shown the way on, not an error, and cannot dismiss it', () => {
    show([{ id: '1', response: 'Confirm your phone number to keep asking.', needsSignIn: true }]);
    expect(screen.getByText('Confirm your number to keep asking')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Not now' })).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

test('a signed-in farmer who left the profile halfway is offered the rest', () => {
  show([{ id: '1', response: 'An answer' }], { user: { user_id: 'f' }, needsOnboarding: true });
  expect(screen.getByText('Finish your farm details')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Add farm details' }));
  expect(openFlow).toHaveBeenCalledWith('profile');
});

describe('a returning farmer\'s home screen', () => {
  const user = { user_id: '+919876543210', name: 'Ramesh Kumar', district: 'Karnal', crops: ['wheat'], total_area_text: '2 acre (0.81 ha)' };
  const turns = [
    { id: 'history-0', prompt: 'Caterpillars in cotton', response: 'a', at: '2026-11-01T05:00:00Z' },
    { id: 'history-2', prompt: 'Mandi price for wheat', response: 'b', at: '2026-11-03T05:00:00Z' },
  ];

  test('welcomes them by name and shows the farm answers are for', () => {
    show(turns, { user, screen: 'home' });
    expect(screen.getByRole('heading', { name: 'Welcome back, Ramesh' })).toBeInTheDocument();
    expect(screen.getByText('Karnal · Wheat · 2 acre (0.81 ha)')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(openFlow).toHaveBeenCalledWith('profile');
  });

  test('lists earlier questions newest first, and opens one', () => {
    show(turns, { user, screen: 'home' });
    const items = screen.getAllByRole('button', { name: /Caterpillars|Mandi price/ });
    expect(items[0]).toHaveTextContent('Mandi price for wheat');
    fireEvent.click(items[1]);
    expect(openTurn).toHaveBeenCalledWith('history-0');
  });

  test('can start a new question', () => {
    show(turns, { user, screen: 'home' });
    fireEvent.click(screen.getByRole('button', { name: 'Ask a new question' }));
    expect(startNewQuestion).toHaveBeenCalled();
  });
});
