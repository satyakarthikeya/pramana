import type { Proof } from "../api";
import { fmtP } from "../format";
import { Check, Cross, Dash } from "./Icons";

/** The badge reflects only the gate result: glyph, fill style and word, never colour alone. */
export function Badge({
  proof,
  single = false,
}: {
  proof: Pick<Proof, "verdict" | "gate_outcome" | "q_value">;
  /** A chat-asked claim: tested alone, so the q-value is not corrected for earlier tests. */
  single?: boolean;
}) {
  if (proof.gate_outcome === "not_testable") {
    return (
      <span className="badge badge-nt" aria-label="Not testable: the claim could not be tested">
        <Dash /> NOT TESTABLE
      </span>
    );
  }
  if (proof.verdict === "PASS") {
    return (
      <span
        className="badge badge-pass"
        aria-label={
          single
            ? `Verified as a single test: q = ${fmtP(proof.q_value)} is below alpha 0.05, not corrected for earlier tests`
            : `Verified: q = ${fmtP(proof.q_value)} is below alpha 0.05 and the effect reached its band`
        }
      >
        <Check /> {single ? "VERIFIED · SINGLE TEST" : "VERIFIED"}
      </span>
    );
  }
  return (
    <span className="badge badge-reject" aria-label="Rejected: the claim did not pass the gate">
      <Cross /> REJECTED
    </span>
  );
}
