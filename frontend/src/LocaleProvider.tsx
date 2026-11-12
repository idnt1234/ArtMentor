import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Globe2 } from "lucide-react";
import { LocaleContext, useLocale } from "./i18n";
import { currentLocale, rememberLocale, translate, translateError, type Locale } from "./locale";

export default function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, updateLocale] = useState(currentLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo(() => ({
    locale,
    setLocale(next: Locale) {
      rememberLocale(next);
      updateLocale(next);
    },
    t: (key: string, values?: Parameters<typeof translate>[2]) => translate(locale, key, values),
    errorText: (message: string) => translateError(locale, message),
  }), [locale]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function LanguageSwitch() {
  const { locale, setLocale, t } = useLocale();
  return (
    <div className="language-switch" role="group" aria-label={t("Language")}>
      <Globe2 size={14} aria-hidden="true" />
      <button type="button" lang="en" aria-pressed={locale === "en"} onClick={() => setLocale("en")}>EN</button>
      <button type="button" lang="zh-CN" aria-pressed={locale === "zh-CN"} onClick={() => setLocale("zh-CN")}>中文</button>
    </div>
  );
}
