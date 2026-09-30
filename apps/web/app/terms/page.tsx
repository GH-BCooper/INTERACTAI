import type { Metadata } from "next";

import { LegalPage } from "@/components/landing/legal-page";

export const metadata: Metadata = { title: "Terms", description: "The terms for using InteractAI." };

export default function TermsPage() {
  return (
    <LegalPage title="Terms of use" updated="September 2026">
      <section>
        <h2>What InteractAI is</h2>
        <p className="mt-2">
          A practice tool. It measures how an answer performs against a rubric its scenario author wrote. It does not predict
          hiring outcomes, certify anyone, or stand in for professional career, legal or medical advice.
        </p>
      </section>
      <section>
        <h2>Fair use</h2>
        <ul className="mt-2">
          <li>Use it to practise for yourself. Don&apos;t use it to record other people without their consent.</li>
          <li>Don&apos;t try to make the interviewer produce harassment or discriminatory questioning; it will refuse.</li>
          <li>Don&apos;t attempt to disrupt the service or access other people&apos;s sessions.</li>
        </ul>
      </section>
      <section>
        <h2>Wellbeing</h2>
        <p className="mt-2">
          If a session touches something that is genuinely distressing, the interviewer will step out of character, end the
          session and point you to support resources. You can also end any session at any time.
        </p>
      </section>
      <section>
        <h2>Your content</h2>
        <p className="mt-2">
          Your recordings, transcripts and reports are yours. See the privacy page for what is stored, for how long, and how to
          export or delete it.
        </p>
      </section>
      <section>
        <h2>No warranty</h2>
        <p className="mt-2">
          InteractAI is an open-source project provided as is. Scores are model judgements and are sometimes wrong, which is why
          each one links to the evidence it is based on.
        </p>
      </section>
    </LegalPage>
  );
}
