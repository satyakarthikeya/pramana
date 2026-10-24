import type { GateOutcome, Proof } from "../api";
import { fmtP } from "../format";
import { useAlpha } from "../hooks";
import { Broken, Check, Cross, Dash } from "./Icons";

export type Presentation = "verified" | "rejected" | "fragile" | "not_testable";

/**
 * How a gate outcome is shown. Exhaustive on purpose: a new outcome is a compile error here,
 * not a silent default that could make an unverified claim look verified.
 */
export function presentation(outcome: GateOutcome): Presentation {
  switch (outcome) {
    case "supported":
      return "verified";
    case "refuted":
    case "negligible":
    case "inconclusive":
      return "rejected";
    case "fragile":
      return "fragile";
    case "not_testable":
      return "not_testable";
    default: {
      const unreachable: never = outcome;
      return unreachable;
    }
  }
}

/** The badge reflects only the gate result: glyph, fill style and word, never colour alone. */
export function Badge({
  proof,
  single = false,
}: {
  proof: Pick<Proof, "verdict" | "gate_outcome" | "q_value">;
  /** A chat-asked claim: tested alone, so the q-value is not corrected for earlier tests. */
  single?: boolean;
}) {
  const alpha = useAlpha();
  const a = alpha === null ? "alpha" : `alpha ${alpha}`;
  const shown = presentation(proof.gate_outcome);
  switch (shown) {
    case "not_testable":
      return (
        <span className="badge badge-nt" aria-label="Not testable: the claim could not be tested">
          <Dash /> NOT TESTABLE
        </span>
      );
    case "fragile":
      return (
        <span
          className="badge badge-fragile"
          aria-label="Not robust: it passed the significance test, but did not hold under a further check"
        >
          <Broken /> NOT ROBUST
        </span>
      );
    case "verified":
      // Defence in depth: a "supported" outcome without a PASS verdict is never drawn as verified.
      if (proof.verdict !== "PASS") break;
      return (
        <span
          className="badge badge-pass"
          aria-label={
            single
              ? `Held up as a single test: q = ${fmtP(proof.q_value)} is below ${a}, not corrected for earlier tests`
              : `Held up: q = ${fmtP(proof.q_value)} is below ${a} and the effect reached its band`
          }
        >
          <Check /> {single ? "HELD UP · SINGLE TEST" : "HELD UP"}
        </span>
      );
    case "rejected":
      break;
    default: {
      const unreachable: never = shown;
      return unreachable;
    }
  }
  return (
    <span className="badge badge-reject" aria-label="Rejected: not enough evidence, or too small an effect, to show as a finding">
      <Cross /> REJECTED
    </span>
  );
}

/** The evidence level of a tested finding, beside the verdict badge. */
export function TestedTag() {
  return <span className="exact-badge tested-badge">TESTED</span>;
}
