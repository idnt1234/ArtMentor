import { createContext, useContext } from "react";
import type { Locale, MessageValues } from "./locale";

export interface LanguageSettings {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, values?: MessageValues) => string;
  errorText: (message: string) => string;
}

export const LocaleContext = createContext<LanguageSettings | null>(null);

export function useLocale(): LanguageSettings {
  const context = useContext(LocaleContext);
  if (!context) throw new Error("LocaleProvider is missing");
  return context;
}
