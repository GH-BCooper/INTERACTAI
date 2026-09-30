import type { Metadata } from "next";

import { LegalPage } from "@/components/landing/legal-page";

export const metadata: Metadata = { title: "Privacy", description: "What InteractAI stores, for how long, and how to delete it." };

/** A plain-language statement of the commitments in CLAUDE.md §10 and docs/17-security-privacy.md
 * — what the product actually does, not boilerplate. */
export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy" updated="September 2026">
      <section>
        <h2>What is stored</h2>
        <ul className="mt-2">
          <li>Your account (email, name, and the sign-in provider you used).</li>
          <li>Your profile: goal, target role, experience level and, only if you paste it, your resume text.</li>
          <li>Each session&apos;s transcript, timings, scores and report.</li>
          <li>Your own audio recording of each session, so you can replay it.</li>
        </ul>
      </section>
      <section>
        <h2>What is never stored</h2>
        <p className="mt-2">
          The interviewer&apos;s voice. It is regenerated from the transcript when you replay a session, so there is no copy of it
          to keep or leak.
        </p>
      </section>
      <section>
        <h2>How long audio is kept</h2>
        <p className="mt-2">
          Recordings expire after 30 days by default. You can choose a shorter window (including deleting immediately after
          scoring) in Settings › Privacy, and you can delete any single recording from its report at any time.
        </p>
      </section>
      <section>
        <h2>Training data</h2>
        <p className="mt-2">
          Your sessions are used to improve scoring only if you turn on training consent in Settings › Privacy. It is separate,
          off by default, never bundled into accepting anything else, and revocable at any time. Transcripts are scrubbed of
          personal details before any human annotator sees them.
        </p>
      </section>
      <section>
        <h2>Export and deletion</h2>
        <p className="mt-2">
          Settings › Privacy exports everything as JSON, and deletes your account. Deletion is genuine: database rows and the
          audio in object storage are both removed.
        </p>
      </section>
    </LegalPage>
  );
}
