import { render, screen } from '@testing-library/react';
import App from './App';

test('renders login header when no token is present', () => {
  render(<App />);
  const headerElement = screen.getByRole('heading', { name: /sign in/i });
  expect(headerElement).toBeInTheDocument();
});

test('applies dark theme class when preference is dark', () => {
  localStorage.setItem('theme', 'dark');
  render(<App />);
  expect(document.documentElement.classList.contains('theme-dark')).toBe(true);
  localStorage.removeItem('theme');
});
