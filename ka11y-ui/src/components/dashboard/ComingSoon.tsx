import { PageHeader } from "@/components/dashboard/PageHeader";
import { Text } from "@/components/ui/Typography";

export function ComingSoon({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <main className="px-4 py-6 sm:px-8 sm:py-8">
        <div className="flex min-h-[50vh] items-center justify-center rounded-2xl bg-surface">
          <Text variant={2} className="text-gray-60">
            {title} is coming soon.
          </Text>
        </div>
      </main>
    </>
  );
}
