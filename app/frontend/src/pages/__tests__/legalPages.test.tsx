import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LangProvider } from '@/components/CustomerLayout';
import AboutPage, {
  ContactPage,
  HelpPage,
  PrivacyPage,
  TermsPage,
  CopyrightPage,
} from '@/pages/AboutPage';

vi.mock('@/lib/dataMode', () => ({
  isMockMode: () => true,
  isApiMode: () => false,
}));

function wrap(ui: React.ReactNode) {
  return render(
    <LangProvider>
      <MemoryRouter>{ui}</MemoryRouter>
    </LangProvider>
  );
}

describe('legal and about pages', () => {
  afterEach(() => cleanup());

  it('renders about with TMDB attribution', () => {
    wrap(<AboutPage />);
    expect(screen.getByTestId('about-page')).toBeTruthy();
    expect(screen.getByTestId('credits-section')).toHaveTextContent(/TMDB/i);
  });

  it('renders contact with real support channels', () => {
    wrap(<ContactPage />);
    expect(screen.getByTestId('contact-email')).toHaveAttribute(
      'href',
      'mailto:support@mobinnet.af'
    );
    expect(screen.getByTestId('contact-web')).toHaveAttribute(
      'href',
      'https://mobinnet.af/contact-us/'
    );
  });

  it('renders help, privacy, terms, and copyright pages', () => {
    wrap(<HelpPage />);
    expect(screen.getByTestId('help-page')).toBeTruthy();
    cleanup();
    wrap(<PrivacyPage />);
    expect(screen.getByTestId('privacy-page')).toBeTruthy();
    cleanup();
    wrap(<TermsPage />);
    expect(screen.getByTestId('terms-page')).toBeTruthy();
    cleanup();
    wrap(<CopyrightPage />);
    expect(screen.getByTestId('copyright-page')).toBeTruthy();
  });
});
