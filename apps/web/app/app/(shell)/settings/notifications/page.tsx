// Task 4.4's Settings > Notifications: "Report-ready and weekly-summary channels." The
// in-app toast (Task 3.1, components/shell/toast-region.tsx) is the one channel that's real
// today; email delivery for either channel needs an email/SMTP provider this project has never
// provisioned (docs/01-SETUP-GUIDE.md has no such account) and is out of scope here — shown
// disabled with an honest label rather than a toggle that persists a preference nothing acts on
// (CLAUDE.md §10: never fabricate).
export default function NotificationsSettingsPage() {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border bg-[var(--bg-card)] p-3">
        <div>
          <p className="text-sm font-medium">In-app: report ready</p>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            A toast appears when a session&apos;s report finishes generating.
          </p>
        </div>
        <span className="text-xs text-[var(--text-tertiary)]">Always on</span>
      </div>

      <div className="flex items-center justify-between rounded-lg border p-3 opacity-60">
        <div>
          <p className="text-sm font-medium">Email: report ready</p>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">Email delivery isn&apos;t set up yet.</p>
        </div>
        <input type="checkbox" disabled title="Coming soon" />
      </div>

      <div className="flex items-center justify-between rounded-lg border p-3 opacity-60">
        <div>
          <p className="text-sm font-medium">Email: weekly summary</p>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">Email delivery isn&apos;t set up yet.</p>
        </div>
        <input type="checkbox" disabled title="Coming soon" />
      </div>
    </div>
  );
}
