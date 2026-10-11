import type { Metadata } from "next";
import "./globals.css";
import AppSidebar from "@/components/AppSidebar";

export const metadata: Metadata = {
  title: "Happy Hour AI",
  description: "AI event planning for cocktail operations — menu, quantities, costs and suppliers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        {/* On desktop the rail is a column beside the content. On mobile the
            same component renders a top bar, which must stack ABOVE the content
            rather than sit beside it — hence flex-col until md. */}
        <div className="flex flex-col md:flex-row min-h-screen">
          <AppSidebar />
          <div className="flex-1 min-w-0">{children}</div>
        </div>
      </body>
    </html>
  );
}
