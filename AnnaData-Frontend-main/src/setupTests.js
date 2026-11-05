import '@testing-library/jest-dom';

// jsdom has no layout, so it does not implement scrolling. The steps scroll to
// the top when they change; in tests that is a no-op.
window.scrollTo = () => {};
