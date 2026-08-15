import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Self-hosted rather than fetched from Google at build time: their CDN rotated
// the Cormorant Garamond file hashes and started 404ing the URLs Next.js had
// cached, which broke the image build for a font that had not changed. A
// variable woff2 covering 400-600 also costs one request instead of six.
const displaySerif = localFont({
  variable: "--font-display-serif",
  display: "swap",
  src: [
    { path: "./fonts/cormorant-garamond-normal.woff2", style: "normal", weight: "400 600" },
    { path: "./fonts/cormorant-garamond-italic.woff2", style: "italic", weight: "400 600" },
  ],
});

export const metadata: Metadata = {
  title: "Whispers of the Wind — Villa Plots at Nandi Valley",
  description:
    "Divyasree Whispers of the Wind: Private Valley villa plots near Nandi Hills, North Bengaluru. Request a call from our advisory team.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${displaySerif.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
