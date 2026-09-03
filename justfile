# Run Fusion Harness against this workspace while keeping the harness itself external.
set dotenv-path := "/root/claude/fusion-harness/.env"
set dotenv-load := true

fusion_harness := env_var_or_default("FUSION_HARNESS_HOME", "/root/claude/fusion-harness")

# Three-slot Fusion stack. Pi and every child agent use this directory as their CWD.
fusion *ARGS:
    pi -e "{{fusion_harness}}/extensions/fusion-harness/fusion-harness.ts" \
        --fh-config "{{fusion_harness}}/.pi/fusion-harness/model-stack-fusion.yaml" \
        {{ARGS}}

# Outage fallback stack (Codex backend 404); see model-stack-fusion-fallback.yaml.
fusion-fallback *ARGS:
    pi -e "{{fusion_harness}}/extensions/fusion-harness/fusion-harness.ts" \
        --fh-config "{{fusion_harness}}/.pi/fusion-harness/model-stack-fusion-fallback.yaml" \
        {{ARGS}}
