import {
  createClient,
  type AuthChangeEvent,
  type Session,
  type SupabaseClient,
  type User,
} from "@supabase/supabase-js";

let client: SupabaseClient | null = null;
let configuredProject = "";

export interface AuthResult {
  user: User | null;
  session: Session | null;
}

export function configureAuth(url: string, publishableKey: string): void {
  const project = `${url}|${publishableKey}`;
  if (client && configuredProject === project) return;
  client = createClient(url, publishableKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      // Keep the SDK on the browser's persistent adapter. The backend's signed
      // HttpOnly bridge remains a bounded fallback when this store is unavailable.
      storage: window.localStorage,
      storageKey: "artmentor-account",
    },
  });
  configuredProject = project;
}

function requireClient(): SupabaseClient {
  if (!client) throw new Error("Account sign-in is not configured for this deployment.");
  return client;
}

export async function currentAuth(): Promise<AuthResult> {
  if (!client) return { user: null, session: null };
  const { data, error } = await client.auth.getSession();
  if (error) throw error;
  return { user: data.session?.user ?? null, session: data.session };
}

export async function authAccessToken(): Promise<string | null> {
  return (await currentAuth()).session?.access_token ?? null;
}

export function listenForAuthChanges(
  listener: (event: AuthChangeEvent, session: Session | null) => void,
): () => void {
  const { data } = requireClient().auth.onAuthStateChange(listener);
  return () => data.subscription.unsubscribe();
}

export async function signInWithPassword(email: string, password: string): Promise<AuthResult> {
  const { data, error } = await requireClient().auth.signInWithPassword({ email, password });
  if (error) throw error;
  return { user: data.user, session: data.session };
}

export async function signUpWithPassword(email: string, password: string): Promise<AuthResult> {
  const { data, error } = await requireClient().auth.signUp({
    email,
    password,
    options: { emailRedirectTo: window.location.origin },
  });
  if (error) throw error;
  return { user: data.user, session: data.session };
}

export async function sendPasswordReset(email: string): Promise<void> {
  const redirectTo = new URL(window.location.href);
  redirectTo.searchParams.set("auth", "recovery");
  const { error } = await requireClient().auth.resetPasswordForEmail(email, {
    redirectTo: redirectTo.toString(),
  });
  if (error) throw error;
}

export async function updatePassword(password: string): Promise<void> {
  const { error } = await requireClient().auth.updateUser({ password });
  if (error) throw error;
  const url = new URL(window.location.href);
  url.searchParams.delete("auth");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

export async function signOutAccount(): Promise<void> {
  const { error } = await requireClient().auth.signOut();
  if (error) throw error;
}
