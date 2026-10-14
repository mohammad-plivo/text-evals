#!/bin/zsh
# Source me before any eval run:   source ../run_env.sh    (from inside cx-skills-gemma31b/)
# Loads .env, mints a fresh 12h LiveKit inference JWT, exports the harness env contract.
EXP_DIR="${0:A:h}"
set -a; source "$EXP_DIR/.env"; set +a

if [ -z "$OPENAI_API_KEY" ]; then
  echo "ERROR: OPENAI_API_KEY is empty in $EXP_DIR/.env" >&2; return 1 2>/dev/null || exit 1
fi

# Agent under test — Gemma-31B via LiveKit hosted inference (US). JWT rides as the bearer key.
export LK_AGENT_MODEL="google/gemma-4-31b-it"
export LK_AGENT_BASE_URL="https://agent-gateway.livekit.cloud/v1"
export LK_AGENT_API_KEY="$("$EXP_DIR/cx-skills-gemma31b/.venv/bin/python" - <<'PY'
import datetime, os
from livekit import api
print((api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
       .with_identity("cx-eval").with_inference_grants(api.InferenceGrants(perform=True))
       .with_ttl(datetime.timedelta(hours=12)).to_jwt()))
PY
)"

# Caller — gpt-4.1-mini on OpenAI (key rides the LK_CALLER_API_KEY slot the harness accepts).
export LK_CALLER_MODEL="gpt-4.1-mini"
export LK_CALLER_BASE_URL="https://api.openai.com/v1"
export LK_CALLER_API_KEY="$OPENAI_API_KEY"

# Judge — gpt-5.5 (OpenAI plugin reads OPENAI_API_KEY directly).
export LK_JUDGE_MODEL="gpt-5.5-1"

echo "env ready: agent=$LK_AGENT_MODEL @ $LK_AGENT_BASE_URL | caller=$LK_CALLER_MODEL | judge=$LK_JUDGE_MODEL | JWT ${#LK_AGENT_API_KEY} chars (12h)"
