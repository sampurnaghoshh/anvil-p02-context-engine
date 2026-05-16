import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Anvil P-02 — Context Engine",
  description: "Persistent Context Engine for AI SRE — shape-based incident matching",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full dark">
      <body className="h-full bg-[#0a0a0a] text-gray-300 font-mono">{children}</body>
    </html>
  );
}
