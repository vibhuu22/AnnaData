import { render, screen, fireEvent } from '@testing-library/react';
import Header from './Header';
import { Auth } from '../../Context/AuthProvider';
import { Context } from '../../Context/ContextProvider';
import { Flow } from '../../Context/Flow';

const openFlow = jest.fn();
const goHome = jest.fn();
const signOut = jest.fn();
const onSignIn = jest.fn();

function show(user) {
  return render(
    <Auth.Provider value={{ user, signOut }}>
      <Context.Provider value={{ screen: 'chat', goHome, responses: [{ id: '1' }] }}>
        <Flow.Provider value={openFlow}>
          <Header onSignIn={onSignIn} />
        </Flow.Provider>
      </Context.Provider>
    </Auth.Provider>
  );
}

test('a guest sees a person icon that opens sign-in, not words', () => {
  show(null);
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(onSignIn).toHaveBeenCalled();
  expect(screen.queryByText('Sign out')).not.toBeInTheDocument();
});

test("a farmer sees their initial, and a menu with who is signed in, their farm, home and sign out", () => {
  show({ name: 'Ramesh Kumar', phone: '+919876543210', district: 'Paschim Medinipur' });
  const avatar = screen.getByRole('button', { name: 'Your account' });
  expect(avatar).toHaveTextContent('R');
  fireEvent.click(avatar);
  expect(screen.getByText('Ramesh Kumar')).toBeInTheDocument();
  expect(screen.getByText('+91 ••••• 43210')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('menuitem', { name: 'Your farm' }));
  expect(openFlow).toHaveBeenCalledWith('profile');
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  fireEvent.click(avatar);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }));
  expect(signOut).toHaveBeenCalled();
});

test('the menu closes on a tap outside and on Escape', () => {
  show({ name: 'Sita', phone: '+919876543210' });
  fireEvent.click(screen.getByRole('button', { name: 'Your account' }));
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Your account' }));
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
});
