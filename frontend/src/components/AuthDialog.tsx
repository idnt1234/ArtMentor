import { useLocale } from "../i18n";
import { LanguageSwitch } from "../LocaleProvider";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  Gauge,
  KeyRound,
  LoaderCircle,
  LogOut,
  Mail,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import {
  sendPasswordReset,
  signInWithPassword,
  signUpWithPassword,
  updatePassword,
} from "../auth";

export type AuthMode = "signin" | "signup" | "forgot" | "reset" | "account";

interface AuthDialogProps {
  open: boolean;
  mode: AuthMode;
  accountEmail: string | null;
  dailyAiLimit: number | null;
  dailyAiRemaining: number | null;
  deletionEnabled: boolean;
  onModeChange: (mode: AuthMode) => void;
  onClose: () => void;
  onAccountChanged: () => Promise<void>;
  onSignOut: () => Promise<void>;
  onExport: () => Promise<void>;
  onDelete: () => Promise<void>;
}

export default function AuthDialog({
  open,
  mode,
  accountEmail,
  dailyAiLimit,
  dailyAiRemaining,
  deletionEnabled,
  onModeChange,
  onClose,
  onAccountChanged,
  onSignOut,
  onExport,
  onDelete,
}: AuthDialogProps) {
  const { t, errorText } = useLocale();
  const [email, setEmail] = useState(accountEmail ?? "");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");

  useEffect(() => {
    if (!open) return;
    setEmail(accountEmail ?? "");
    setPassword("");
    setConfirmation("");
    setError(null);
    setNotice(null);
    setDeleteConfirmation("");
  }, [open, mode, accountEmail]);

  if (!open) return null;

  const submit = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === "signin") {
        await signInWithPassword(email.trim(), password);
        await onAccountChanged();
        onClose();
      } else if (mode === "signup") {
        if (password.length < 8) throw new Error("Use at least 8 characters for your password.");
        if (password !== confirmation) throw new Error("The two passwords do not match.");
        const result = await signUpWithPassword(email.trim(), password);
        if (result.session) {
          await onAccountChanged();
          onClose();
        } else {
          setNotice("Check your email to verify the account, then return here to sign in.");
        }
      } else if (mode === "forgot") {
        await sendPasswordReset(email.trim());
        setNotice("If that address has an account, a password-reset email is on its way.");
      } else if (mode === "reset") {
        if (password.length < 8) throw new Error("Use at least 8 characters for your password.");
        if (password !== confirmation) throw new Error("The two passwords do not match.");
        await updatePassword(password);
        await onAccountChanged();
        setNotice("Your password has been updated.");
        onModeChange("account");
      }
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    setBusy(true);
    setError(null);
    try {
      await onSignOut();
      onClose();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const exportData = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await onExport();
      setNotice("Your account export is downloading.");
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const deleteData = async () => {
    if (deleteConfirmation !== "DELETE") return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await onDelete();
      onClose();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const title = {
    signin: "Welcome back.",
    signup: "Keep your work with you.",
    forgot: "Reset your password.",
    reset: "Choose a new password.",
    account: "Your ArtMentor account.",
  }[mode];

  return (
    <div className="auth-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title">
        <button className="auth-close" onClick={onClose} aria-label={t("Close account dialog")}><X size={18} /></button>
        <div className="auth-language"><LanguageSwitch /></div>
        <span className="auth-icon">{mode === "account" ? <UserRound size={22} /> : <KeyRound size={22} />}</span>
        <p className="eyebrow">{t("ArtMentor account")}</p>
        <h2 id="auth-title">{t(title)}</h2>

        {mode === "account" ? (
          <div className="account-summary">
            <span><Mail size={17} /></span>
            <div><small>{t("Signed in as")}</small><strong>{accountEmail}</strong></div>
            <p>{t("Your critique history is available on every device where you sign in.")}</p>
            {dailyAiLimit !== null && (
              <div className="account-usage">
                <Gauge size={16} />
                <span><strong>{t("{remaining} of {limit}", { remaining: dailyAiRemaining ?? 0, limit: dailyAiLimit })}</strong><small>{t("AI actions remaining today · resets 00:00 UTC")}</small></span>
              </div>
            )}
            <button className="auth-secondary" onClick={() => void exportData()} disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={17} /> : <Download size={17} />}
              {t("Download my data")}
            </button>
            <button className="auth-secondary danger" onClick={signOut} disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={17} /> : <LogOut size={17} />}
              {t("Sign out")}
            </button>
            <div className="delete-account">
              <strong>{t("Delete account")}</strong>
              <p>{t("This permanently removes your ArtMentor work and sign-in identity. Download your data first if you want a copy.")}</p>
              <label><span>{t("Type DELETE to confirm")}</span><input value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} placeholder="DELETE" autoComplete="off" /></label>
              <button className="auth-secondary danger" onClick={() => void deleteData()} disabled={busy || !deletionEnabled || deleteConfirmation !== "DELETE"}>
                {busy ? <LoaderCircle className="spin" size={17} /> : <Trash2 size={17} />}
                {t("Permanently delete account")}
              </button>
              {!deletionEnabled && <small>{t("Deletion is not yet configured on this deployment. Contact the operator.")}</small>}
            </div>
          </div>
        ) : (
          <form onSubmit={(event) => { event.preventDefault(); void submit(); }}>
            {(mode === "signin" || mode === "signup" || mode === "forgot") && (
              <label><span>{t("Email address")}</span><input type="email" required autoFocus value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" /></label>
            )}
            {(mode === "signin" || mode === "signup" || mode === "reset") && (
              <label><span>{mode === "reset" ? t("New password") : t("Password")}</span><input type="password" required minLength={8} autoFocus={mode === "reset"} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === "signin" ? "current-password" : "new-password"} /></label>
            )}
            {(mode === "signup" || mode === "reset") && (
              <label><span>{mode === "reset" ? t("Confirm new password") : t("Confirm password")}</span><input type="password" required minLength={8} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" /></label>
            )}
            <button className="primary-action" disabled={busy || (mode !== "reset" && !email.trim())} type="submit">
              {busy ? <LoaderCircle className="spin" size={18} /> : mode === "forgot" ? <Mail size={18} /> : <KeyRound size={18} />}
              {mode === "signin" ? t("Sign in") : mode === "signup" ? t("Create account") : mode === "forgot" ? t("Send reset email") : t("Update password")}
            </button>
          </form>
        )}

        {notice && <p className="auth-notice" role="status"><CheckCircle2 size={16} />{t(notice)}</p>}
        {error && <p className="auth-error" role="alert">{errorText(error)}</p>}

        {mode === "signin" && <div className="auth-links"><button onClick={() => onModeChange("forgot")}>{t("Forgot password?")}</button><button onClick={() => onModeChange("signup")}>{t("Create an account")}</button></div>}
        {mode === "signup" && <button className="auth-back" onClick={() => onModeChange("signin")}><ArrowLeft size={15} /> {" "}{t("Already have an account?")}</button>}
        {mode === "forgot" && <button className="auth-back" onClick={() => onModeChange("signin")}><ArrowLeft size={15} /> {" "}{t("Back to sign in")}</button>}
        {mode === "reset" && <p className="auth-help">{t("This recovery session came from your secure email link.")}</p>}
      </section>
    </div>
  );
}
