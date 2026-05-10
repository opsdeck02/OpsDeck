import type { Metadata } from "next";
import "leaflet/dist/leaflet.css";
import "./globals.css";

const siteUrl = new URL("https://www.opsdeck.in");

export const metadata: Metadata = {
  metadataBase: siteUrl,
  title: "OpsDeck | Continuity Intelligence for Industrial Operations",
  description:
    "OpsDeck predicts, prioritizes, and explains operational risk before it impacts production.",
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: "OpsDeck | Continuity Intelligence for Industrial Operations",
    description:
      "OpsDeck predicts, prioritizes, and explains operational risk before it impacts production.",
    url: "/",
    siteName: "OpsDeck",
    type: "website",
    // TODO: Replace this fallback with /og-image.png when a branded raster share asset is available.
    images: [
      {
        url: "/steelops-dashboard-screenshot.png",
        width: 1200,
        height: 630,
        alt: "OpsDeck continuity intelligence interface",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "OpsDeck | Continuity Intelligence for Industrial Operations",
    description:
      "OpsDeck predicts, prioritizes, and explains operational risk before it impacts production.",
    images: ["/steelops-dashboard-screenshot.png"],
  },
  icons: {
    icon: "/favicon.svg",
    apple: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
