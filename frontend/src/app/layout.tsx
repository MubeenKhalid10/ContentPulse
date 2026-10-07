import type { Metadata } from "next";
import { Archivo, Geist, Martian_Mono } from "next/font/google";

import { Providers } from "@/components/providers";
import "./globals.css";

// UI text.
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

// Headlines: a condensed news grotesk (Archivo's width axis).
const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  axes: ["wdth"],
});

// Slug lines, datelines, timestamps and scores: teleprinter mono.
const martianMono = Martian_Mono({
  variable: "--font-martian-mono",
  subsets: ["latin"],
  axes: ["wdth"],
});

export const metadata: Metadata = {
  title: { default: "ContentPulse", template: "%s · ContentPulse" },
  description:
    "ContentPulse reads the trend wire for each client, keeps what fits their services, and carries it to an approved post.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${archivo.variable} ${martianMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
