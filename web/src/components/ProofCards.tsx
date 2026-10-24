import type { AttackOutcome, AttackResult, PermutationScheme, Proof, SplitRecord } from "../api";
import { fmtEffect, fmtInt, fmtP, metricSymbol } from "../format";
import { useAlpha } from "../hooks";
import { Broken, Check, Dash } from "./Icons";

/** The null hypothesis in words, from how the gate built it. Exhaustive over the schemes. */
export function nullInWords(scheme: PermutationScheme): string {
  switch (scheme) {
    case "free":
      return "rows shuffled";
    case "block_differenced":
      return "period-to-period changes resampled in blocks";
    case "stratified":
      return "shuffled only within each period";
    case "cluster":
      return "labels moved between whole entities";
    case "paired":
      return "each entity compared with itself";
    default: {
      const unreachable: never = scheme;
      return unreachable;
    }
  }
}

function splitWords(split: SplitRecord | null | undefined): string {
  if (!split) return "The split of rows was not recorded for this result.";
  const total = split.n_exploration + split.n_confirmation;
  if (split.method === "none") {
    return `No rows were held back from exploration: all ${fmtInt(total)} rows were used.`;
  }
  const how: Record<Exclude<SplitRecord["method"], "none">, string> = {
    random_rows: "chosen at random",
    by_time: "the latest periods",
    by_entity: "whole entities",
  };
  return `Tested on ${fmtInt(split.n_confirmation)} of ${fmtInt(total)} rows held back from exploration (${how[split.method]}; seed ${split.seed}).`;
}

function outcomeWord(outcome: AttackOutcome): string {
  switch (outcome) {
    case "survived":
      return "SURVIVED";
    case "broken":
      return "BROKE";
    case "not_run":
      return "NOT RUN";
    default: {
      const unreachable: never = outcome;
      return unreachable;
    }
  }
}

function AttackGlyph({ outcome }: { outcome: AttackOutcome }) {
  switch (outcome) {
    case "survived":
      return <Check />;
    case "broken":
      return <Broken />;
    case "not_run":
      return <Dash />;
    default: {
      const unreachable: never = outcome;
      return unreachable;
    }
  }
}

function AttackRow({ attack }: { attack: AttackResult }) {
  const ran = attack.outcome !== "not_run";
  return (
    <li className="attack" data-outcome={attack.outcome}>
      <span className="attack-tag">
        <AttackGlyph outcome={attack.outcome} />{" "}
        {attack.outcome === "not_run" && attack.applicable === false
          ? "N/A"
          : outcomeWord(attack.outcome)}
      </span>
      <span>
        <b>
          {attack.attack_id} {attack.name}
        </b>
        {attack.outcome === "not_run"
          ? attack.applicable === false
            ? ": does not apply here: "
            : ": could not run: "
          : ": "}
        {attack.reason}
        {ran && attack.original_effect !== null && attack.attacked_effect !== null && (
          <span className="mono attack-nums">
            {" "}
            effect {fmtEffect(attack.original_effect)} to {fmtEffect(attack.attacked_effect)}
            {attack.n_rows !== null ? `, n = ${fmtInt(attack.n_rows)}` : ""}
          </span>
        )}
      </span>
    </li>
  );
}

/** The broken attack, if any, for a claim that passed and then failed. */
export function brokenAttack(proof: Pick<Proof, "attacks">): AttackResult | undefined {
  return proof.attacks?.find((a) => a.outcome === "broken");
}

/**
 * Four plain-word cards for one proof: luck, size, rows and attacks. Every figure is read from
 * the proof object; nothing is computed here and nothing is marked survived unless it ran.
 */
export function ProofCards({
  proof,
  effectBand,
  single = false,
}: {
  proof: Proof;
  effectBand: string | null;
  /** A chat-asked claim: its q-value is the raw p-value of a family of one. */
  single?: boolean;
}) {
  const alpha = useAlpha();
  const attacks = proof.attacks ?? [];
  const ran = attacks.filter((a) => a.outcome !== "not_run");
  const survived = ran.filter((a) => a.outcome === "survived").length;
  const notRun = attacks.filter((a) => a.outcome === "not_run");
  const tested = proof.q_value !== null;
  const below = tested && alpha !== null ? (proof.q_value as number) < alpha : null;
  const scheme = proof.permutation_scheme;

  return (
    <div className="proof-cards">
      <section className="proof-card" aria-label="Could it be luck?">
        <span className="label">Could it be luck?</span>
        {tested ? (
          <>
            <p>
              {single ? "q (equal to the raw p for a single test)" : "q"} = <b className="mono">{fmtP(proof.q_value)}</b>
              {alpha !== null && (
                <>
                  , {below ? "below" : "not below"} the cutoff alpha ={" "}
                  <span className="mono">{alpha}</span>
                </>
              )}
              . Raw p = <span className="mono">{fmtP(proof.p_value)}</span>.
            </p>
            <p className="explain">
              The chance comparison:{" "}
              {scheme ? nullInWords(scheme) : "how the null was built was not recorded for this result"}.
            </p>
          </>
        ) : (
          <p className="explain">No test was run on this claim, so there is no p-value or q-value.</p>
        )}
      </section>

      <section className="proof-card" aria-label="How big?">
        <span className="label">How big?</span>
        {proof.effect_size !== null ? (
          <p>
            Effect {metricSymbol(proof.effect_metric)} ={" "}
            <b className="mono">{fmtEffect(proof.effect_size)}</b>
            {effectBand ? <>, a <b>{effectBand}</b> effect</> : null}.
          </p>
        ) : (
          <p className="explain">No effect size: the claim was not tested.</p>
        )}
        {proof.effect_interval ? (
          <p className="explain">
            Repeating the study, the effect would likely fall between{" "}
            <span className="mono">{fmtEffect(proof.effect_interval.low)}</span> and{" "}
            <span className="mono">{fmtEffect(proof.effect_interval.high)}</span> (
            {Math.round(proof.effect_interval.confidence * 100)}% interval, resampling{" "}
            {{
              row_bootstrap: "rows",
              entity_bootstrap: "whole entities",
              period_bootstrap: "whole periods",
            }[proof.effect_interval.method]}
            ).
          </p>
        ) : null}
      </section>

      <section className="proof-card" aria-label="Which rows?">
        <span className="label">Which rows?</span>
        <p>{splitWords(proof.split)}</p>
      </section>

      <section className="proof-card" aria-label="Attacks">
        <span className="label">Attacks</span>
        {attacks.length === 0 ? (
          <p className="explain">
            {proof.verdict === "PASS"
              ? "No attacks are recorded for this result."
              : "Attacks are tried only on claims that pass the gate."}
          </p>
        ) : (
          <>
            <p>
              <b>
                Survived {survived} of {ran.length}
              </b>
              {ran.length === 1 ? " attack" : " attacks"} that ran
              {notRun.length > 0 ? `; ${notRun.length} not run` : ""}.
            </p>
            <ul className="attack-list">
              {attacks.map((a) => (
                <AttackRow key={a.attack_id} attack={a} />
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}
