import type {
  AttackOutcome,
  AttackResult,
  ForecastEvidence,
  PermutationScheme,
  Proof,
  SplitRecord,
} from "../api";
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
    case "block_sign_flip":
      return "the method's and the baseline's errors swapped for whole blocks of backtest origins";
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
  const reuse =
    split.prior_looks && split.prior_looks > 0
      ? split.look_budget != null && split.prior_looks > split.look_budget
        ? ` These rows were already used by ${split.prior_looks} earlier runs on this table, more than the usual ${split.look_budget}, so treat this result as less independent of what was asked before.`
        : ` ${split.prior_looks} earlier ${split.prior_looks === 1 ? "run" : "runs"} on this table used the same rows.`
      : "";
  return `Tested on ${fmtInt(split.n_confirmation)} of ${fmtInt(total)} rows held back from exploration (${how[split.method]}; seed ${split.seed}).${reuse}`;
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

const METHOD_WORDS: Record<ForecastEvidence["method"], string> = {
  trend_seasonal: "linear trend with seasonal dummies",
  holt_winters: "Holt-Winters exponential smoothing",
};

/**
 * The backtest behind a forecast claim, in plain words and a small table. Past accuracy on
 * periods the method did not see: nothing here says what the next periods will be.
 */
export function ForecastCard({ forecast }: { forecast: ForecastEvidence }) {
  const baseline = forecast.baseline === "seasonal_naive" ? "seasonal-naive" : "last-value";
  const unit = forecast.period === "quarter" ? "quarters" : "months";
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  const rows = forecast.origins.slice(-12);
  return (
    <section className="proof-card" aria-label="Backtest">
      <span className="label">Backtest</span>
      <p>
        {METHOD_WORDS[forecast.method]}, scored on {fmtInt(forecast.n_origins)} origins from{" "}
        <span className="mono">{forecast.first_origin}</span> to{" "}
        <span className="mono">{forecast.last_origin}</span>, {forecast.horizon} {unit} ahead each.
        Scaled error <b className="mono">{forecast.mase_model.toFixed(2)}</b> against{" "}
        <span className="mono">{forecast.mase_baseline.toFixed(2)}</span> for the {baseline}{" "}
        forecast: <b>{pct(forecast.error_reduction)}</b> less error.
      </p>
      {forecast.horizon > 1 && (
        <p className="explain">
          Error reduction by horizon:{" "}
          <span className="mono">
            {forecast.horizon_reductions.map((r, i) => `${i + 1}: ${pct(r)}`).join(", ")}
          </span>
          .
        </p>
      )}
      {forecast.reduction_vs_last_value !== null && forecast.baseline === "seasonal_naive" && (
        <p className="explain">
          Against a last-value forecast the same method had{" "}
          <span className="mono">{pct(forecast.reduction_vs_last_value)}</span> less error.
        </p>
      )}
      {forecast.interval_coverage !== null && forecast.interval_level !== null && (
        <p className="explain">
          The {pct(forecast.interval_level)} range built on the earlier origins covered{" "}
          <span className="mono">{pct(forecast.interval_coverage)}</span> of the later ones
          {forecast.interval_calibrated === false
            ? ": accuracy held up, but the stated range is not calibrated."
            : "."}
        </p>
      )}
      {rows.length > 0 && (
        <table className="data-table" aria-label="Last backtest origins: actual and forecast">
          <thead>
            <tr>
              <th scope="col">Forecast for</th>
              <th scope="col">Ahead</th>
              <th scope="col" className="num">Actual</th>
              <th scope="col" className="num">Method</th>
              <th scope="col" className="num">{baseline}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.origin}-${r.horizon}`}>
                <td className="mono">{r.target}</td>
                <td className="mono">{r.horizon}</td>
                <td className="num mono">{r.actual.toLocaleString("en-US", { maximumFractionDigits: 1 })}</td>
                <td className="num mono">{r.forecast.toLocaleString("en-US", { maximumFractionDigits: 1 })}</td>
                <td className="num mono">{r.baseline.toLocaleString("en-US", { maximumFractionDigits: 1 })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="explain">{forecast.disclaimer}</p>
    </section>
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
              origin_block_bootstrap: "blocks of backtest origins",
            }[proof.effect_interval.method]}
            ).
          </p>
        ) : null}
      </section>

      {proof.forecast ? <ForecastCard forecast={proof.forecast} /> : null}

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
