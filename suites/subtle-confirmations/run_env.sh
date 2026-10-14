#!/bin/zsh
# Source me before an eval run:   source ../run_env.sh    (from inside cx-skills-subtle/)
# Reuses the 31B-Experiments creds (LiveKit + Azure). Mints a fresh 12h LiveKit inference JWT.
# Agent under test is switchable:  AGENT=gemma31b (default)  |  AGENT=gpt41  (GPT-4.1 on Azure)
SUBTLE_DIR="${0:A:h}"
ENV_FILE="$SUBTLE_DIR/../31B-Experiments/.env"
VENV="$SUBTLE_DIR/cx-skills-subtle/.venv"
set -a; source "$ENV_FILE"; set +a

if [ -z "$OPENAI_API_KEY" ]; then
  echo "ERROR: OPENAI_API_KEY empty in $ENV_FILE" >&2; return 1 2>/dev/null || exit 1
fi

AGENT="${AGENT:-gpt41}"   # switched to OpenAI gpt-4.1 (production agent model); AGENT=gemma31b for the old arm
if [ "$AGENT" = "gpt41" ]; then
  # Agent = GPT-4.1 on Azure (same resource as caller/judge; harness with_azure path via AZURE_OPENAI_ENDPOINT)
  export LK_AGENT_MODEL="gpt-4.1"
  export LK_AGENT_BASE_URL="$AZURE_OPENAI_ENDPOINT"
  export LK_AGENT_API_KEY="$OPENAI_API_KEY"
else
  # Agent = Gemma-31B via LiveKit hosted inference (US). 12h JWT rides as the bearer key.
  export LK_AGENT_MODEL="google/gemma-4-31b-it"
  export LK_AGENT_BASE_URL="https://agent-gateway.livekit.cloud/v1"
  export LK_AGENT_API_KEY="$("$VENV/bin/python" - <<'PY'
import datetime, os
from livekit import api
print((api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
       .with_identity("cx-eval").with_inference_grants(api.InferenceGrants(perform=True))
       .with_ttl(datetime.timedelta(hours=12)).to_jwt()))
PY
)"
fi

# Caller — gpt-4.1-mini on Azure (harness with_azure keyed on AZURE_OPENAI_ENDPOINT)
# Agent temperature — 0.7 (the intended setting; 0.3 default makes phrasing mode-collapse). Overridable.
export LK_AGENT_TEMP=0.7  # hard-locked (was default-0.7); confirmation humanization runs at 0.7

export LK_CALLER_MODEL="gpt-4.1-mini"
export LK_CALLER_BASE_URL="https://api.openai.com/v1"
export LK_CALLER_API_KEY="$OPENAI_API_KEY"

# Judge — gpt-5.5 (Azure deployment gpt-5.5-1)
export LK_JUDGE_MODEL="gpt-5.5-1"

echo "env ready: AGENT=$AGENT model=$LK_AGENT_MODEL | caller=$LK_CALLER_MODEL | judge=$LK_JUDGE_MODEL | key ${#LK_AGENT_API_KEY} chars"
