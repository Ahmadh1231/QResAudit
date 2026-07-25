# V3/V4 portable platform

The V3/V4 layer is deterministic and solver-independent. `GaussianProcessSurrogate`
uses a squared-exponential covariance with explicit predictive uncertainty, and
`active_learning_candidates` uses a seeded lower/upper confidence bound inside
validated bounds. The robust-design API samples correlated fabrication errors and
returns output distributions, quantiles, a feasibility fraction, uncertainty,
sensitivity, and provenance.

`make_cpw_design` creates an SI-unit portable design specification. It does not
create proprietary CAD. Thermal, strain, and magnetic helpers state their
first-order approximations and propagate independent supplied uncertainties.

Digital-twin calibration only updates parameters from caller-supplied measured
frequency/Q evidence. Literature records never invent a citation: a missing
source identifier remains `None`, and evidence quality is explicit.

`plan_design` and `RuleBasedDesignAgent` are local rule-based behavior. They do
not claim an LLM, external solver, HPC job, or experiment ran. `SimulationLoop`
requires an explicit approval flag and `allow_external=True` before submission,
and blocks analysis/optimization until evidence is validated. Checkpoints are
JSON and resumable.
