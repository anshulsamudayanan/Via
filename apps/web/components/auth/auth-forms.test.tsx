import { ApiError } from "@via/api-client";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { me, mockClient, navigation, renderWith, router } from "@/test/helpers";

import { ForgotPasswordForm } from "./forgot-password-form";
import { LoginForm } from "./login-form";
import { RegisterForm } from "./register-form";
import { ResetPasswordForm } from "./reset-password-form";

describe("LoginForm", () => {
  it("signs in and follows a safe ?next", async () => {
    navigation.search = new URLSearchParams("next=/projects/p1");
    const client = mockClient({ auth: { login: vi.fn().mockResolvedValue(me) } });
    renderWith(<LoginForm />, client, false);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), " ada@example.com ");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(client.auth.login).toHaveBeenCalledWith({ email: "ada@example.com", password: "correct horse battery" });
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/projects/p1"));
  });

  it("ignores external ?next targets", async () => {
    navigation.search = new URLSearchParams("next=//evil.example");
    const client = mockClient({ auth: { login: vi.fn().mockResolvedValue(me) } });
    renderWith(<LoginForm />, client, false);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "x");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows the API's error message", async () => {
    const login = vi.fn().mockRejectedValue(new ApiError(401, "invalid_credentials", "Invalid email or password."));
    renderWith(<LoginForm />, mockClient({ auth: { login } }), false);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Invalid email or password.");
    expect(router.replace).not.toHaveBeenCalled();
  });
});

describe("RegisterForm", () => {
  it("validates locally before calling the API", async () => {
    const register = vi.fn();
    renderWith(<RegisterForm />, mockClient({ auth: { register } }), false);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Enter your name.")).toBeTruthy();
    expect(screen.getByText("Enter a valid email address.")).toBeTruthy();
    expect(screen.getByText("Use at least 10 characters.")).toBeTruthy();
    expect(register).not.toHaveBeenCalled();
  });

  it("creates the account and goes to the dashboard", async () => {
    const register = vi.fn().mockResolvedValue(me);
    renderWith(<RegisterForm />, mockClient({ auth: { register } }), false);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Name"), "Ada Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(register).toHaveBeenCalledWith({ display_name: "Ada Lovelace", email: "ada@example.com", password: "correct horse battery" });
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("puts a taken email error on the email field", async () => {
    const register = vi.fn().mockRejectedValue(new ApiError(409, "email_taken", "An account with this email already exists."));
    renderWith(<RegisterForm />, mockClient({ auth: { register } }), false);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Name"), "Ada");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    const email = screen.getByLabelText("Email");
    await waitFor(() => expect(email.getAttribute("aria-invalid")).toBe("true"));
    expect(screen.getByText("An account with this email already exists.")).toBeTruthy();
  });
});

describe("password reset", () => {
  it("request form shows the neutral confirmation", async () => {
    const requestPasswordReset = vi.fn().mockResolvedValue({ message: "If an account exists for that email, a reset link has been sent." });
    renderWith(<ForgotPasswordForm />, mockClient({ auth: { requestPasswordReset } }), false);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect((await screen.findByRole("status")).textContent).toContain("If an account exists");
  });

  it("confirm form checks the passwords match and submits the token", async () => {
    navigation.search = new URLSearchParams("token=abc123token456token789");
    const confirmPasswordReset = vi.fn().mockResolvedValue({ message: "ok" });
    renderWith(<ResetPasswordForm />, mockClient({ auth: { confirmPasswordReset } }), false);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("New password"), "brand new secret 9");
    await user.type(screen.getByLabelText("Confirm new password"), "different secret 9");
    await user.click(screen.getByRole("button", { name: "Set new password" }));
    expect(screen.getByText("Passwords don't match.")).toBeTruthy();
    await user.clear(screen.getByLabelText("Confirm new password"));
    await user.type(screen.getByLabelText("Confirm new password"), "brand new secret 9");
    await user.click(screen.getByRole("button", { name: "Set new password" }));
    expect(confirmPasswordReset).toHaveBeenCalledWith("abc123token456token789", "brand new secret 9");
    expect((await screen.findByRole("status")).textContent).toContain("Your password has been changed.");
  });

  it("confirm form explains a missing token", () => {
    renderWith(<ResetPasswordForm />, mockClient(), false);
    expect(screen.getByText("Reset link missing")).toBeTruthy();
  });
});
