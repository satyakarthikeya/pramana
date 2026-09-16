"""Executor tests: the import policy, the subprocess, and the provenance stamp.

Every test here asks the same question in a different way: can anything that is not a
verified number from `pramana.verification.stats` reach the gate? The answer has to be
no on every path -- crash, timeout, silence, malformed JSON, forged result.

`test_hand_rolled_permutation_is_rejected` is the one that matters most. It is the
attack the import whitelist alone does NOT stop, and the reason the provenance stamp
exists at all.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pramana.contracts.enums import ClaimType, TestType
from pramana.verification.config import VerificationConfig, load_config
from pramana.verification.executor.policy import ImportPolicyViolation, check_imports
from pramana.verification.executor.runner import execute
from pramana.verification.falsification.generator import (
    FalsificationProgram,
    generate_from_template,
)
from tests.fixtures.candidates import TRUE_CORRELATION
from tests.fixtures.frames import toy_frame

ALLOWED = ["numpy", "pandas", "pramana.verification.stats"]


@pytest.fixture(scope="module")
def config() -> VerificationConfig:
    shipped = load_config()
    return shipped.model_copy(
        update={"statistics": shipped.statistics.model_copy(update={"n_permutations": 1000})}
    )


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return toy_frame()


def _program(source: str) -> FalsificationProgram:
    return FalsificationProgram(
        insight_id="c-forged",
        claim_type=ClaimType.CORRELATION,
        var_x="age",
        var_y="bmi",
        test_type=TestType.PERMUTATION,
        n_permutations=1000,
        seed=7,
        source=source,
        generator="test",
    )


# --- static import policy -------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "import scipy",
        "import scipy.stats",
        "from scipy import stats",
        "from scipy.stats import spearmanr",
        "import statsmodels.api",
        "from sklearn.linear_model import LinearRegression",
    ],
)
def test_statistics_libraries_are_blocked(source: str) -> None:
    with pytest.raises(ImportPolicyViolation, match="generated code requests"):
        check_imports(source, ALLOWED)


@pytest.mark.parametrize(
    "source",
    [
        "x = __import__('scipy')",
        "import importlib\nimportlib.import_module('scipy')",
        "exec('import scipy')",
        "eval('1+1')",
        "compile('import scipy', '<s>', 'exec')",
        "open('/etc/passwd')",
        "().__class__.__subclasses__()",
    ],
)
def test_dynamic_escape_hatches_are_blocked(source: str) -> None:
    """Blocking `import scipy` is pointless if `__import__("scipy")` still works."""
    with pytest.raises(ImportPolicyViolation):
        check_imports(source, ALLOWED)


def test_permitted_imports_pass() -> None:
    check_imports(
        "import numpy as np\nimport pandas as pd\n"
        "from pramana.verification.stats import permutation_test, spearman_rho\n",
        ALLOWED,
    )


def test_submodule_of_a_permitted_package_passes() -> None:
    check_imports("from pramana.verification.stats.permutation import permutation_test", ALLOWED)


def test_unparseable_source_is_a_violation() -> None:
    """Code we cannot read is code we cannot vouch for."""
    with pytest.raises(ImportPolicyViolation, match="does not parse"):
        check_imports("def falsify(frame)\n    return", ALLOWED)


def test_relative_imports_are_refused() -> None:
    with pytest.raises(ImportPolicyViolation, match="relative import"):
        check_imports("from . import something", ALLOWED)


# --- fail-closed execution ------------------------------------------------


def test_the_real_template_runs_and_verifies(
    config: VerificationConfig, frame: pd.DataFrame
) -> None:
    result = execute(generate_from_template(TRUE_CORRELATION, config), frame, config)
    assert result.ok
    assert result.payload is not None
    assert 0.0 < result.payload["p_value"] <= 1.0
    assert result.payload["provenance"], "a real run must carry a stamp"


def test_crash_fails_closed(config: VerificationConfig, frame: pd.DataFrame) -> None:
    program = _program("def falsify(frame):\n    raise RuntimeError('boom')\n")
    result = execute(program, frame, config)
    assert not result.ok
    assert "exited with status" in (result.failure_reason or "")
    assert result.payload is None


def test_timeout_fails_closed(config: VerificationConfig, frame: pd.DataFrame) -> None:
    """An infinite loop must be killed and reported, never waited on forever."""
    impatient = config.model_copy(
        update={"executor": config.executor.model_copy(update={"timeout_seconds": 2})}
    )
    program = _program("def falsify(frame):\n    while True:\n        pass\n")
    result = execute(program, frame, impatient)
    assert not result.ok
    assert "timeout" in (result.failure_reason or "")


def test_no_output_fails_closed(config: VerificationConfig, frame: pd.DataFrame) -> None:
    program = _program("def falsify(frame):\n    return None\n")
    result = execute(program, frame, config)
    assert not result.ok


def test_missing_keys_fail_closed(config: VerificationConfig, frame: pd.DataFrame) -> None:
    program = _program("def falsify(frame):\n    return {'p_value': 0.01}\n")
    result = execute(program, frame, config)
    assert not result.ok
    assert "missing required keys" in (result.failure_reason or "")


def test_p_value_of_zero_fails_closed(config: VerificationConfig, frame: pd.DataFrame) -> None:
    """A permutation p-value is add-one floored, so exact zero is impossible and
    signals a number that did not come from the real test.
    """
    program = _program(
        "def falsify(frame):\n"
        "    return {'p_value': 0.0, 'effect_size': 0.9, 'effect_metric': 'spearman_rho',\n"
        "            'reported_effect': 0.9, 'seed': 7, 'statistic': 0.9,\n"
        "            'n_permutations': 1000, 'provenance': 'x'}\n"
    )
    result = execute(program, frame, config)
    assert not result.ok
    assert "p_value" in (result.failure_reason or "")


def test_unknown_effect_metric_fails_closed(
    config: VerificationConfig, frame: pd.DataFrame
) -> None:
    program = _program(
        "def falsify(frame):\n"
        "    return {'p_value': 0.01, 'effect_size': 0.9, 'effect_metric': 'my_own_metric',\n"
        "            'reported_effect': 0.9, 'seed': 7, 'statistic': 0.9,\n"
        "            'n_permutations': 1000, 'provenance': 'x'}\n"
    )
    result = execute(program, frame, config)
    assert not result.ok
    assert "vetted gating metrics" in (result.failure_reason or "")


def test_import_violation_never_reaches_the_subprocess(
    config: VerificationConfig, frame: pd.DataFrame
) -> None:
    program = _program("import scipy\ndef falsify(frame):\n    return {}\n")
    result = execute(program, frame, config)
    assert not result.ok
    assert "import policy violation" in (result.failure_reason or "")


# --- the provenance stamp -------------------------------------------------


def test_fabricated_result_is_rejected(config: VerificationConfig, frame: pd.DataFrame) -> None:
    """Well-formed, plausible, entirely invented. No stamp, no evidence."""
    program = _program(
        "def falsify(frame):\n"
        "    return {'p_value': 0.0001, 'effect_size': 0.85, 'effect_metric': 'spearman_rho',\n"
        "            'reported_effect': 0.85, 'seed': 7, 'statistic': 0.85,\n"
        "            'n_permutations': 1000, 'provenance': 'deadbeef'}\n"
    )
    result = execute(program, frame, config)
    assert not result.ok
    assert "provenance check failed" in (result.failure_reason or "")


def test_hand_rolled_permutation_is_rejected(
    config: VerificationConfig, frame: pd.DataFrame
) -> None:
    """THE hole the import whitelist does not close.

    This code imports nothing forbidden. It uses numpy and pandas only, computes a
    real Spearman correlation via `DataFrame.corr` -- which needs no scipy -- and runs
    a genuine shuffle loop. The number it produces may even be roughly right. It is
    still refused, because it did not come from the audited function, and "roughly
    right" is not a property the gate can verify.
    """
    program = _program(
        "import numpy as np\n"
        "import pandas as pd\n"
        "\n"
        "def falsify(frame):\n"
        "    pair = frame[['age', 'bmi']].dropna()\n"
        "    observed = pair.corr(method='spearman').iloc[0, 1]\n"
        "    rng = np.random.default_rng(7)\n"
        "    shuffled = pair['bmi'].to_numpy(dtype=float).copy()\n"
        "    x = pair['age'].to_numpy(dtype=float)\n"
        "    extreme = 0\n"
        "    for _ in range(200):\n"
        "        rng.shuffle(shuffled)\n"
        "        null = pd.Series(x).corr(pd.Series(shuffled), method='spearman')\n"
        "        extreme += abs(null) >= abs(observed)\n"
        "    return {'p_value': (1 + extreme) / 201, 'effect_size': float(observed),\n"
        "            'effect_metric': 'spearman_rho', 'reported_effect': float(observed),\n"
        "            'seed': 7, 'statistic': float(observed), 'n_permutations': 200,\n"
        "            'provenance': None}\n"
    )
    result = execute(program, frame, config)
    assert not result.ok
    assert "provenance check failed" in (result.failure_reason or "")


def test_stamp_does_not_verify_against_a_different_run(
    config: VerificationConfig, frame: pd.DataFrame
) -> None:
    """Nonces are per execution, so a stamp captured from one run cannot be replayed
    into the next. Two runs of the same program must produce different stamps.
    """
    program = generate_from_template(TRUE_CORRELATION, config)
    first = execute(program, frame, config)
    second = execute(program, frame, config)
    assert first.ok and second.ok
    assert first.payload is not None and second.payload is not None
    assert first.payload["p_value"] == second.payload["p_value"], "same seed, same result"
    assert first.payload["provenance"] != second.payload["provenance"], "different nonce"
