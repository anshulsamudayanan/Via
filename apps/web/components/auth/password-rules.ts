/** Mirrors the API's rules (apps/api/src/via_api/security.py) for instant feedback. */
export const MIN_PASSWORD_LENGTH = 10;
export const MAX_PASSWORD_LENGTH = 128;

export function passwordError(password: string, email?: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) return `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (password.length > MAX_PASSWORD_LENGTH) return `Use at most ${MAX_PASSWORD_LENGTH} characters.`;
  if (!password.trim()) return "Password cannot be only whitespace.";
  if (email && password.toLowerCase() === email.trim().toLowerCase()) return "Password must not be your email address.";
  return null;
}

export function emailError(email: string): string | null {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim()) ? null : "Enter a valid email address.";
}
