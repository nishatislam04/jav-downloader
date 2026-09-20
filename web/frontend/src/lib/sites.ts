export type SiteInfo = {
  name: string;
  domain: string;
  url: string;
  /** Pinned sites are ours — always shown at the top of the list. */
  pinned?: boolean;
};

export const SITES: SiteInfo[] = [
  { name: "jav.guru", domain: "jav.guru", url: "https://jav.guru", pinned: true },
  { name: "SpankBang", domain: "spankbang.com", url: "https://spankbang.com", pinned: true },
  { name: "MissAV", domain: "missav.ai", url: "https://missav.ai" },
  { name: "SupJav", domain: "supjav.com", url: "https://supjav.com" },
  { name: "JableTV", domain: "jable.tv", url: "https://jable.tv" },
  { name: "Hanime1", domain: "hanime1.me", url: "https://hanime1.me" },
];

export function siteFaviconSrc(domain: string): string {
  return `https://icons.duckduckgo.com/ip3/${domain}.ico`;
}
