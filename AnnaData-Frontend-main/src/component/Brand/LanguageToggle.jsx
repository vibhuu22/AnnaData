import React from 'react';
import { useUiLanguage, setUiLanguage } from '../../Config/uiLanguage';

export default function LanguageToggle() {
  const language = useUiLanguage();
  return <button type="button" onClick={() => setUiLanguage(language === 'hi' ? 'en' : 'hi')}
    lang={language === 'hi' ? 'en' : 'hi'}
    aria-label={language === 'hi' ? 'Switch interface to English' : 'इंटरफ़ेस हिंदी में बदलें'}
    className="min-h-touch shrink-0 rounded-full border border-leaf-600 bg-white/80 px-3 text-sm font-semibold text-leaf-800">
    {language === 'hi' ? 'English' : 'हिंदी'}
  </button>;
}
