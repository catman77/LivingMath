#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m unittest discover -s tests -v
python3 reference_oracles/oracle_substrings.py >/dev/null
python3 reference_oracles/independent_native_reference.py >/dev/null
python3 reference_oracles/frozen_counterfactual.py >/dev/null
python3 reference_oracles/factorial_frontier.py >/dev/null
printf 'REFERENCE_ORACLES_OK (does not certify the future MCP patch)\n'
