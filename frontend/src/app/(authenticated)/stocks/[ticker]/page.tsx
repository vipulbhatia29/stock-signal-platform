import { StockDetailClient } from "./stock-detail-client";

export default async function StockDetailPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;

  return <StockDetailClient ticker={ticker.toUpperCase()} />;
}
