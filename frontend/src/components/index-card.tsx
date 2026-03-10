import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MetricCard } from "@/components/metric-card";

interface IndexCardProps {
  name: string;
  slug: string;
  stockCount: number;
  description: string | null;
}

export function IndexCard({
  name,
  slug,
  stockCount,
  description,
}: IndexCardProps) {
  return (
    <Link href={`/screener?index=${slug}`}>
      <Card className="cursor-pointer transition-colors hover:border-foreground/20">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">{name}</CardTitle>
          {description && (
            <CardDescription className="text-xs">{description}</CardDescription>
          )}
        </CardHeader>
        <CardContent>
          <MetricCard
            label="stocks"
            value={stockCount}
            valueClassName="text-2xl font-semibold tabular-nums"
          />
        </CardContent>
      </Card>
    </Link>
  );
}

export function IndexCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-4 w-24" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-8 w-16" />
        <Skeleton className="mt-1 h-3 w-12" />
      </CardContent>
    </Card>
  );
}
