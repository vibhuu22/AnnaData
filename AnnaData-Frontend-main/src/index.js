import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';
import AuthProvider from './Context/AuthProvider';
import ContextProvider from './Context/ContextProvider';

// AuthProvider is outside ContextProvider because the conversation belongs to
// whoever is signed in: the identity has to exist before the chat can load that
// farmer's history, and signing out has to be able to throw the chat away.
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <AuthProvider>
    <ContextProvider>
      <App />
    </ContextProvider>
  </AuthProvider>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
