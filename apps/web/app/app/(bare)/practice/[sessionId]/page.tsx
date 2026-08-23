import { PracticeRoom } from "@/components/practice/practice-room";

export default async function PracticePage({
  params,
  searchParams,
}: {
  params: Promise<{ sessionId: string }>;
  searchParams: Promise<{ onboarding?: string }>;
}) {
  const { sessionId } = await params;
  const { onboarding } = await searchParams;
  return (
    <PracticeRoom
      sessionId={sessionId}
      micDeniedExit={
        onboarding === "1" ? { label: "Skip for now — go to your dashboard", href: "/app" } : undefined
      }
    />
  );
}
