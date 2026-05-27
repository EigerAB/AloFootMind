import { createI18n } from 'vue-i18n'
import zh from './zh'
import en from './en'

const savedLocale = localStorage.getItem('locale') ?? 'zh'

export const i18n = createI18n({
  legacy: false,
  locale: savedLocale,
  fallbackLocale: 'en',
  messages: { zh, en },
})

export function setLocale(lang: 'zh' | 'en') {
  i18n.global.locale.value = lang
  localStorage.setItem('locale', lang)
  document.documentElement.lang = lang
}

export type LocaleKey = 'zh' | 'en'
