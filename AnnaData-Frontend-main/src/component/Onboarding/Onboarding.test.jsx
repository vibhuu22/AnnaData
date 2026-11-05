import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Onboarding from './Onboarding';
import { Auth } from '../../Context/AuthProvider';
import { saveProfile } from '../../Config/session';

jest.mock('../../Config/session', () => ({ saveProfile: jest.fn() }));

const onboarded = jest.fn();
const setUser = jest.fn();
const onDone = jest.fn();
const FARMER = { user_id: '+919876543210', phone: '+919876543210', crops: ['cotton'] };

function show(props = {}) {
  return render(
    <Auth.Provider value={{ user: FARMER, onboarded, setUser }}>
      <Onboarding onDone={onDone} {...props} />
    </Auth.Provider>
  );
}
beforeEach(() => {
  jest.clearAllMocks();
  window.scrollTo = jest.fn();
  saveProfile.mockResolvedValue({ user: FARMER });
});

test('About you, then Your farm, with the crop they asked about already picked', async () => {
  show();
  expect(screen.getByText('Number confirmed · +91 ••••• 43210')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Ramesh' } });
  fireEvent.click(screen.getByRole('button', { name: 'FPO' }));
  fireEvent.change(screen.getByPlaceholderText('Group name (optional)'), { target: { value: 'Kisan Sangh' } });
  fireEvent.click(screen.getByRole('button', { name: 'Next: your farm' }));

  await screen.findByRole('heading', { name: 'Your farm' });
  expect(saveProfile).toHaveBeenCalledWith({
    name: 'Ramesh', language: null, farmer_group: 'fpo', farmer_group_name: 'Kisan Sangh',
  });
  // Step one alone does not finish onboarding.
  expect(onboarded).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Cotton' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByText('Cotton is already picked from the question you asked.')).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('District'), { target: { value: 'Karnal' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save farm details' }));
  await waitFor(() => expect(onDone).toHaveBeenCalled());
  expect(onboarded).toHaveBeenCalledWith(FARMER);
  expect(saveProfile).toHaveBeenLastCalledWith(expect.objectContaining({ district: 'Karnal', crops: ['cotton'] }));
});

test('a crop not on the list can be added', async () => {
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Next: your farm' }));
  await screen.findByRole('heading', { name: 'Your farm' });
  fireEvent.click(screen.getByRole('button', { name: '+ Other' }));
  fireEvent.change(screen.getByLabelText('Another crop'), { target: { value: 'Chilli' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add' }));
  expect(screen.getByRole('button', { name: 'Chilli' })).toHaveAttribute('aria-pressed', 'true');
});

test('Skip leaves at once and is remembered, so they are not asked again', async () => {
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
  await waitFor(() => expect(onDone).toHaveBeenCalled());
  expect(onboarded).toHaveBeenCalled();
  expect(Object.keys(saveProfile.mock.calls[0][0])).toEqual(['took_ms']);
});

test('editing an existing profile closes without saving anything', () => {
  show({ editing: true });
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(onDone).toHaveBeenCalled();
  expect(saveProfile).not.toHaveBeenCalled();
});

test('Back returns from Your farm to About you', async () => {
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Next: your farm' }));
  await screen.findByRole('heading', { name: 'Your farm' });
  fireEvent.click(screen.getByRole('button', { name: 'Back' }));
  expect(screen.getByRole('heading', { name: 'About you' })).toBeInTheDocument();
});
