import { Languages } from 'lucide-react'
import { useI18n } from '../i18n/context'
import { localeNames } from '../i18n/catalogs'
import type { Locale } from '../types'

const locales: Locale[] = ['ru', 'en', 'es']

export function LanguageSwitch() {
  const { locale, setLocale } = useI18n()
  return (
    <div className="language-switch" aria-label="Language">
      <Languages size={15} aria-hidden="true" />
      {locales.map((item) => (
        <button key={item} className={locale === item ? 'is-active' : ''} onClick={() => setLocale(item)}>
          {localeNames[item]}
        </button>
      ))}
    </div>
  )
}
