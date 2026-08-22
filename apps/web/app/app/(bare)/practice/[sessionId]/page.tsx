import { PracticeRoom } from "@/components/practice/practice-room";

export default async function PracticePage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <PracticeRoom sessionId={sessionId} />;
}
