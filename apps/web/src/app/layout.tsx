import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { StudioNav } from "@/components/studio/studio-nav";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Visual Studio — Product composite",
  description:
    "SDXL product photography: generate, correction jobs, and GPU-backed inpaint",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <body className="studio-gradient flex min-h-full flex-col">
        <TooltipProvider delayDuration={200}>
          <StudioNav />
          {children}
        </TooltipProvider>
      </body>
    </html>
  );
}
