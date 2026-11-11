import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import Main, { revealCut } from './Main';
import { Auth } from '../../Context/AuthProvider';
import { Context } from '../../Context/ContextProvider';
import { Flow } from '../../Context/Flow';
import { rateAnswer } from '../../Config/session';
import { speak } from '../../Config/speech';

jest.mock('../../Config/session', () => ({ saveProfile: jest.fn(), rateAnswer: jest.fn(() => Promise.resolve({ stored: true })) }));
jest.mock('../../Config/speech', () => ({
  speak: jest.fn(), stopSpeaking: jest.fn(), isSpeechSupported: () => false, unlockAudio: jest.fn(),
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

  test('the microphone opens voice mode', () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: jest.fn(() => new Promise(() => {})) },
    });
    show();
    fireEvent.click(screen.getByRole('button', { name: 'Talk to AnnaData' }));
    expect(screen.getByRole('dialog', { name: 'Voice conversation' })).toBeInTheDocument();
    delete navigator.mediaDevices;
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

describe('what an answer still needs', () => {
  test('a missing crop is asked for, the way SMS asks it', () => {
    show([{ id: '1', response: 'An answer', missingSlots: ['crop'] }]);
    expect(screen.getByText('Tell us your crop for advice specific to it.')).toBeInTheDocument();
  });

  test('a missing location offers to use the phone\'s', () => {
    show([{ id: '1', response: 'An answer', needsLocation: true }]);
    expect(screen.getByText(/Tell us your village or district/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Use my location' })).toBeInTheDocument();
  });

  test('asked in the language the answer is in', () => {
    show([{ id: '1', response: 'गेहूं में पीला रतुआ है। प्रोपिकोनाज़ोल डालें।', missingSlots: ['crop'] }]);
    expect(screen.getByText('अपनी फ़सल का नाम बताइए, ताकि सलाह आपकी फ़सल के हिसाब से हो।')).toBeInTheDocument();
  });

  test('a Hinglish answer is asked in Hinglish', () => {
    show([{ id: '1', response: 'Gehu ki buwai November mein karein, aur beej upchar zaroor karein.', needsLocation: true }]);
    expect(screen.getByText(/Apna gaon ya zila bataiye/)).toBeInTheDocument();
  });

  test('the phone\'s place is offered once as the farm, answered with one tap', () => {
    show([{ id: '1', response: 'Use Mancozeb for blight.', missingSlots: [], needsLocation: false, confirmPlace: 'Kharagpur' }]);
    expect(screen.getByText('Is your farm near Kharagpur?')).toBeInTheDocument();
    expect(screen.queryByText(/Tell us your village or district/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
    expect(send).toHaveBeenCalledWith({ text: 'Yes' });
  });

  test('and in the answer\'s language', () => {
    show([{ id: '1', response: 'Aloo mein jhulsa rog hai, aap Mancozeb ka chhidkav karein.', confirmPlace: 'Kharagpur' }]);
    expect(screen.getByText('Kya aapka khet Kharagpur ke paas hai?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Nahi' }));
    expect(send).toHaveBeenCalledWith({ text: 'Nahi' });
  });

  test('nothing is asked when nothing is missing', () => {
    show([{ id: '1', response: 'An answer', missingSlots: [], needsLocation: false }]);
    expect(screen.queryByText(/Tell us your/)).not.toBeInTheDocument();
  });
});

describe('an answer being written', () => {
  test('fills in as it arrives, with nothing that needs the whole answer', () => {
    show([{ id: '1', prompt: 'q', response: 'Pehla vakya.', streaming: true, doseStatus: 'available' }]);
    expect(screen.getByText('Pehla vakya.')).toBeInTheDocument();
    expect(screen.getByText('Writing…')).toBeInTheDocument();
    expect(screen.queryByText('Approved dose')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Yes, useful' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add farm details' })).not.toBeInTheDocument();
  });
});

describe('a new answer is written out', () => {
  test('word by word, with what needs the whole answer waiting until it is done', async () => {
    const text = 'Gehu ki buwai November ke pehle pakhwade mein karein, aur beej upchar zaroor karein.';
    show([{ id: '1', prompt: 'q', response: text, live: true, doseStatus: 'available' }]);
    expect(screen.getByText('Writing…')).toBeInTheDocument();
    expect(screen.queryByText('Approved dose')).not.toBeInTheDocument();
    expect(screen.queryByText(text)).not.toBeInTheDocument();
    expect(await screen.findByText('Approved dose', {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.queryByText('Writing…')).not.toBeInTheDocument();
  });

  test('once, not again when the farmer comes back to the chat from News', async () => {
    const text = 'Dhaan mein ek baar 25 kg potash prati acre daalein, baali nikalne se pehle.';
    const turn = { id: 'back-1', prompt: 'q', response: text, live: true, doseStatus: 'available' };
    const first = show([turn]);
    expect(await screen.findByText('Approved dose', {}, { timeout: 4000 })).toBeInTheDocument();
    first.unmount();
    show([turn]);
    expect(screen.queryByText('Writing…')).not.toBeInTheDocument();
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  test('an answer left half-written is shown whole on return', () => {
    const text = 'Sarson ki buwai 15 October tak kar lein. Uske baad paidavaar ghat sakti hai, isliye jaldi karein.';
    const turn = { id: 'back-2', prompt: 'q', response: text, live: true };
    const first = show([turn]);
    expect(screen.getByText('Writing…')).toBeInTheDocument();
    first.unmount();
    show([turn]);
    expect(screen.queryByText('Writing…')).not.toBeInTheDocument();
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  test('bold is never left open half-way through', () => {
    expect(revealCut('Use **Acephate 75% SP** now', 15)).toBe('Use **Acephate**');
  });
});

describe('rating an answer', () => {
  test('one tap records it and says thanks', async () => {
    show([{ id: '1', prompt: 'q', response: 'An answer' }]);
    fireEvent.click(screen.getByRole('button', { name: 'No, not useful' }));
    await waitFor(() => expect(rateAnswer).toHaveBeenCalledWith(false));
    expect(screen.getByText(/Thanks for telling us/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Yes, useful' })).not.toBeInTheDocument();
  });
});

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
    { id: 'history-0', chatId: 'c1', prompt: 'Caterpillars in cotton', response: 'a', at: '2026-11-01T05:00:00Z' },
    { id: 'history-2', chatId: 'c2', prompt: 'Mandi price for wheat', response: 'b', at: '2026-11-03T05:00:00Z' },
  ];
  const chats = [
    { id: 'c2', title: 'Mandi price for wheat', at: '2026-11-03T05:00:00Z', count: 1 },
    { id: 'c1', title: 'Caterpillars in cotton', at: '2026-11-01T05:00:00Z', count: 2 },
  ];
  const showHome = () => render(
    <Auth.Provider value={{ user, needsOnboarding: false }}>
      <Context.Provider value={{ thread: [], responses: turns, chats, screen: 'home', input: '', setInput: jest.fn(), send, newChat, openChat, focusId: null, loading: false }}>
        <Flow.Provider value={openFlow}>
          <Main />
        </Flow.Provider>
      </Context.Provider>
    </Auth.Provider>
  );
  const newChat = jest.fn();
  const openChat = jest.fn();

  test('welcomes them by name and shows the farm answers are for', () => {
    showHome();
    expect(screen.getByRole('heading', { name: 'Welcome back, Ramesh' })).toBeInTheDocument();
    expect(screen.getByText('Karnal · Wheat · 2 acre (0.81 ha)')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(openFlow).toHaveBeenCalledWith('profile');
  });

  test('lists their chats, newest first, and opens one', () => {
    showHome();
    const items = screen.getAllByRole('button', { name: /Caterpillars|Mandi price/ });
    expect(items[0]).toHaveTextContent('Mandi price for wheat');
    expect(items[1]).toHaveTextContent('2 questions');
    fireEvent.click(items[1]);
    expect(openChat).toHaveBeenCalledWith('c1');
  });

  test('can start a new chat', () => {
    showHome();
    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    expect(newChat).toHaveBeenCalled();
  });
});

describe('explore and news', () => {
  const at = (view) => render(
    <Auth.Provider value={{ user: null }}>
      <Context.Provider value={{ thread: [], responses: [], chats: [], screen: view, input: '', setInput: jest.fn(), send, newChat: jest.fn(), focusId: null, loading: false }}>
        <Flow.Provider value={openFlow}>
          <Main />
        </Flow.Provider>
      </Context.Provider>
    </Auth.Provider>
  );

  test('an explore tile starts a chat with its example question', () => {
    at('explore');
    expect(screen.getByRole('heading', { name: 'Mandi prices' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '“Aaj gehu ka mandi bhav kya hai?”' }));
    expect(send).toHaveBeenCalledWith({ text: 'Aaj gehu ka mandi bhav kya hai?', image: undefined });
  });

  test('an explore tile reads its example aloud, without asking it', () => {
    at('explore');
    fireEvent.click(screen.getByRole('button', { name: 'Listen: Aaj gehu ka mandi bhav kya hai?' }));
    expect(speak).toHaveBeenCalledWith('Aaj gehu ka mandi bhav kya hai?', 'hi-IN');
    expect(send).not.toHaveBeenCalled();
  });

  test('explore carries the bottom bar, whose microphone opens voice mode', () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: jest.fn(() => new Promise(() => {})) },
    });
    at('explore');
    const bar = screen.getByRole('navigation', { name: 'Main' });
    fireEvent.click(within(bar).getByRole('button', { name: 'Talk' }));
    expect(screen.getByRole('dialog', { name: 'Voice conversation' })).toBeInTheDocument();
    delete navigator.mediaDevices;
  });
});

describe('the ask screen, new parts', () => {
  test('an example can be heard before it is asked', () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: 'Listen: Gehu ki buwai kab karein?' }));
    expect(speak).toHaveBeenCalledWith('Gehu ki buwai kab karein?', 'hi-IN');
    expect(send).not.toHaveBeenCalled();
  });

  test('the bottom bar opens the menu from "More"', () => {
    const setMenuOpen = jest.fn();
    render(
      <Auth.Provider value={{ user: null }}>
        <Context.Provider value={{ thread: [], responses: [], chats: [], screen: 'ask', input: '', setInput: jest.fn(), send, setMenuOpen, focusId: null, loading: false }}>
          <Flow.Provider value={openFlow}>
            <Main />
          </Flow.Provider>
        </Context.Provider>
      </Auth.Provider>
    );
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('button', { name: 'More' }));
    expect(setMenuOpen).toHaveBeenCalledWith(true);
  });

  test('recent chats appear on the front door and open', () => {
    const openChat = jest.fn();
    render(
      <Auth.Provider value={{ user: null }}>
        <Context.Provider value={{ thread: [], responses: [], chats: [{ id: 'c1', title: 'Gehu ki buwai kab karein?' }], openChat, screen: 'ask', input: '', setInput: jest.fn(), send, focusId: null, loading: false }}>
          <Flow.Provider value={openFlow}>
            <Main />
          </Flow.Provider>
        </Context.Provider>
      </Auth.Provider>
    );
    const recent = screen.getByRole('region', { name: 'Recent chats' });
    fireEvent.click(within(recent).getByRole('button', { name: 'Gehu ki buwai kab karein?' }));
    expect(openChat).toHaveBeenCalledWith('c1');
  });
});
