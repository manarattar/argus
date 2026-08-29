import { Card, Skeleton } from '@/components/ui/primitives';

export default function Loading() {
  return (
    <div className="space-y-5">
      <div>
        <Skeleton className="h-3 w-24" />
        <Skeleton className="mt-2.5 h-7 w-72" />
        <Skeleton className="mt-2.5 h-3.5 w-[32rem]" />
      </div>
      <Card>
        <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <div key={index}>
              <Skeleton className="h-2.5 w-20" />
              <Skeleton className="mt-2 h-7 w-16" />
            </div>
          ))}
        </div>
      </Card>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <Skeleton className="h-4 w-40" />
          <div className="mt-4 space-y-2.5">
            {[0, 1, 2, 3, 4].map((index) => (
              <Skeleton key={index} className="h-9 w-full" />
            ))}
          </div>
        </Card>
        <Card>
          <Skeleton className="h-4 w-32" />
          <div className="mt-4 space-y-2.5">
            {[0, 1, 2].map((index) => (
              <Skeleton key={index} className="h-6 w-full" />
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
