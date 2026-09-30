import type { Metadata } from "next";
import { Suspense } from "react";

import { ReportView } from "@/components/report/report-view";

export const metadata: Metadata = { title: "Report" };

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={null}>
      <ReportView sessionId={id} />
    </Suspense>
  );
}
