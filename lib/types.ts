export type Region = {
  id: string;
  nameZh: string;
};

export type SourceInfo = {
  id: string;
  name: string;
  nameZh: string;
  country: string;
  region: string;
  homepage: string;
  fetchedCount: number;
  lastStatus: "ok" | "error" | "empty" | string;
  lastError: string | null;
};

export type Story = {
  id: string;
  url: string;
  discussionUrl?: string | null;
  country?: string;
  region: string;
  tags: string[];
  tasteScore?: number;
  sourceId: string;
  sourceName: string;
  sourceNameZh: string;
  title: string;
  titleZh: string;
  summary: string;
  summaryZh: string;
  image: string;
  imageCredit: string;
  publishedAt: string | null;
  fetchedAt: string;
};

export type Payload = {
  generatedAt: string;
  regions: Region[];
  sources: SourceInfo[];
  stories: Story[];
};
