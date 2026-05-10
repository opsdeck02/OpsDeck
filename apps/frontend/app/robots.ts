import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/api/",
        "/dashboard/",
        "/login",
        "/auth/",
        "/internal/",
      ],
    },
    sitemap: "https://www.opsdeck.in/sitemap.xml",
  };
}
