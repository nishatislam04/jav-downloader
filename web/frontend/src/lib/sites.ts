export type SiteInfo = {
  name: string;
  domain: string;
  url: string;
};

// Sites are listed in display order — the first entries appear at the top.
export const SITES: SiteInfo[] = [
  { name: "jav.guru", domain: "jav.guru", url: "https://jav.guru" },
  { name: "SpankBang", domain: "spankbang.com", url: "https://spankbang.com" },
  { name: "MissAV", domain: "missav.ai", url: "https://missav.ai" },
  { name: "SupJav", domain: "supjav.com", url: "https://supjav.com" },
  { name: "JableTV", domain: "jable.tv", url: "https://jable.tv" },
  { name: "Hanime1", domain: "hanime1.me", url: "https://hanime1.me" },
];

export function siteFaviconSrc(domain: string): string {
  return `https://icons.duckduckgo.com/ip3/${domain}.ico`;
}

/** Backend site labels ("JavGuru", "SiteMissAV", "SiteJableTV_Backup") → SITES entry. */
export function siteFromLabel(label: string | undefined | null): SiteInfo | undefined {
  if (!label) return undefined;
  const key = label
    .replace(/^site/i, "")
    .replace(/_?backup$/i, "")
    .replace(/[^a-z0-9]/gi, "")
    .toLowerCase();
  if (!key) return undefined;
  return SITES.find((site) => site.name.replace(/[^a-z0-9]/gi, "").toLowerCase() === key);
}
