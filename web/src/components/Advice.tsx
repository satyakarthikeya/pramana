import type { Explanation, FindingReview } from "../api";

/** The plain-language sentence for a finding, with who wrote it and why, never hidden. */
export function PlainWords({ explanation }: { explanation: Explanation }) {
  return (
    <div className="advice">
      <div className="chips">
        <span className="chip">
          {explanation.source === "model"
            ? "MODEL WORDING, CHECKED BY CODE · THE FACTS LINE IS THE RECORD"
            : "WRITTEN BY CODE FROM THE PROOF"}
        </span>
      </div>
      <p className="advice-text">{explanation.text}</p>
      {explanation.fallback_reason && (
        <p className="explain">
          A model was switched on, but the code-written sentence is shown instead:{" "}
          {explanation.fallback_reason}.
        </p>
      )}
    </div>
  );
}

/** One line for the finding card: how many other columns may account for part of it. */
export function CaveatLine({ review }: { review: FindingReview }) {
  if (review.status === "flagged") {
    const n = review.caveats.length;
    return (
      <p className="explain" role="note">
        Worth checking: {n} other {n === 1 ? "column" : "columns"} may account for part of this.
        Open the proof for the numbers.
      </p>
    );
  }
  if (review.status === "none_found") {
    return (
      <p className="explain">
        Checked {review.controls_checked} other columns; none weakened this association.
      </p>
    );
  }
  return <p className="explain">Confound check not run: {review.reason}.</p>;
}

/** The full confound check: each caveat with its numbers, and questions for a NEXT run. */
export function ConfoundCheck({ review }: { review: FindingReview }) {
  const skipped =
    review.skipped_near_duplicates > 0
      ? `, and skipped ${review.skipped_near_duplicates} that look like the same measurement`
      : "";
  return (
    <div className="advice">
      {review.status === "not_checked" && <p className="explain">Not checked: {review.reason}.</p>}
      {review.status === "none_found" && (
        <p className="explain">
          Checked {review.controls_checked} other columns{skipped}. None of them weakened this
          association when rows were compared at a similar value.
        </p>
      )}
      {review.status === "flagged" && (
        <>
          <p className="explain">
            Checked {review.controls_checked} other columns{skipped}. These may account for part of
            this finding. The verdict is unchanged.
            {review.reason ? ` Note: ${review.reason}.` : ""}
          </p>
          <ul className="caveats">
            {review.caveats.map((c) => (
              <li key={c.control}>
                <div className="chips">
                  <span className="chip">col: {c.control}</span>
                  <span className="chip">n={c.n}</span>
                  <span className="chip">
                    {c.measure === "spearman_rho" ? "rank correlation" : "rank eta-squared"}{" "}
                    {c.before.toFixed(2)} → {c.after.toFixed(2)}
                  </span>
                </div>
                <p className="advice-text">{c.text}</p>
                {c.follow_ups.length > 0 && (
                  <>
                    <span className="label">Questions for a next run</span>
                    <ul className="followups">
                      {c.follow_ups.map((f) => (
                        <li key={f.sentence}>{f.sentence}</li>
                      ))}
                    </ul>
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
