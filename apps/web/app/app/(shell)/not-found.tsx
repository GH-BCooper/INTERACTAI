import { SearchX } from "lucide-react";

import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/primitives";

export default function ShellNotFound() {
  return (
    <div className="mx-auto max-w-lg px-4 py-16 sm:px-6">
      <EmptyState
        icon={<SearchX size={18} />}
        title="We couldn't find that"
        body="It may have been deleted, or the link may belong to a different account."
        action={
          <ButtonLink href="/app" variant="primary" size="sm">
            Back to dashboard
          </ButtonLink>
        }
      />
    </div>
  );
}
