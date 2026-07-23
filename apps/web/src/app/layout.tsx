import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ordy — the AI waiter",
  description: "The AI waiter that understands, talks, and takes action.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
