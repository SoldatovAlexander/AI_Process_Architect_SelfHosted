import { useMemo, useState, type ReactNode } from 'react'
import type { Locale } from '../types'
import { catalogs } from './catalogs'
import { I18nContext, type I18nValue } from './context'

function initialLocale(): Locale {
  const stored = localStorage.getItem('apa_locale')
  return stored === 'en' || stored === 'es' ? stored : 'ru'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, updateLocale] = useState<Locale>(initialLocale)
  const value = useMemo<I18nValue>(() => ({
    locale,
    setLocale: (next) => {
      localStorage.setItem('apa_locale', next)
      document.documentElement.lang = next
      updateLocale(next)
    },
    t: (key) => catalogs[locale][key],
  }), [locale])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}
