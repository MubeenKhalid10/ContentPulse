import { z } from "zod";

export const loginSchema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

const newPassword = z
  .string()
  .min(10, "Use at least 10 characters.")
  .max(128, "Use at most 128 characters.");

export const registerSchema = z.object({
  full_name: z.string().trim().min(1, "Enter your name.").max(200),
  email: z.email("Enter a valid email address."),
  password: newPassword,
});

export const acceptInviteSchema = (hasAccount: boolean) =>
  z.object({
    full_name: z.string().trim().min(1, "Enter your name.").max(200),
    password: hasAccount ? z.string().min(1, "Enter your current password.") : newPassword,
  });

export const forgotPasswordSchema = z.object({
  email: z.email("Enter a valid email address."),
});

export const resetPasswordSchema = z
  .object({ password: newPassword, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match." });

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;
