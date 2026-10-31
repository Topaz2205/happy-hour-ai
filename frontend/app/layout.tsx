import type { Metadata } from "next";
import "./globals.css";
import AuthGate from "@/components/AuthGate";

export const metadata: Metadata = {
  title: "Happy Hour Cocktails AI",
  description: "AI event planning for cocktail operations — menu, quantities, costs and suppliers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        {/* Sidebar and layout live in AuthGate, so the sign-in pages render
            without the app chrome. */}
        <AuthGate>{children}</AuthGate>
      </body>
    </html>
  );
}
