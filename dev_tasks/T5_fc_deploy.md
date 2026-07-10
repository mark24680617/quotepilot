# Task T5: Alibaba Cloud Function Compute (FC 3.0) deployment files for QuotePilot

Produce the deployment kit for hosting QuotePilot's FastAPI dashboard
(`quotepilot.web.app:app`) on Alibaba Cloud **Function Compute 3.0** as a
**custom-runtime Web Function**, deployed with **Serverless Devs** (`s` CLI,
`fc3` component). These facts were researched against current Alibaba Cloud
international docs — follow them exactly:

- Web Function = custom runtime hosting our own HTTP server, which MUST
  listen on **0.0.0.0:9000**.
- Region: **ap-southeast-1** (Singapore), international account.
- The runtime image's system python3 is old → attach the official public
  **Python 3.10 layer** and put its bin dir first in PATH. Use a `layers:`
  entry with a placeholder ARN and a loud comment telling the deployer to
  paste the region's current Python310 public layer ARN (find it in the FC
  console → Layers → Public layers).
- Third-party deps are vendored into the code package under `./vendor` via:
  `pip install -r deploy/requirements.txt -t vendor --platform manylinux2014_x86_64 --only-binary=:all:`
  and exposed with env `PYTHONPATH=/code/vendor:/code/src`.
- Secrets/config via function environment variables; s.yaml supports
  `${env(NAME)}` interpolation from the deployer's shell.
- Writable filesystem on FC is ONLY /tmp → set `QP_RUNS_DIR=/tmp/runs`
  (the app already honors this env var).
- HTTP trigger with `authType: anonymous` gives a public
  `https://<random>.<region>.fcapp.run` URL.

## Files to output

### 1. `s.yaml` (project root)
Serverless Devs v3 config, `fc3` component. One function `quotepilot`:
- `runtime: custom`, `customRuntimeConfig` with `command: ["/code/bootstrap"]`
  and `port: 9000`
- `region: ap-southeast-1` via a `vars` block; `access: default`
- `cpu: 0.35`, `memorySize: 512`, `diskSize: 512`, `timeout: 300`,
  `instanceConcurrency: 10`
- `environmentVariables`:
  `QWEN_API_KEY: ${env(QWEN_API_KEY)}`,
  `QWEN_BASE_URL: https://dashscope-intl.aliyuncs.com/compatible-mode/v1`,
  `QP_RUNS_DIR: /tmp/runs`,
  `PYTHONPATH: /code/vendor:/code/src`,
  `PATH: /opt/python3.10/bin:/usr/local/bin:/usr/bin:/bin` (layer bin first)
- `layers:` with placeholder ARN + comment as described above
- `code: ./` with an `ignore`/exclude note if the component supports it
  (exclude .venv, .git, runs, .dev_staging, tests, docs) — if fc3 lacks an
  exclude key, add a comment pointing at `deploy/package.sh` which builds a
  clean staging dir instead.
- `triggers:` one `http` trigger, `authType: anonymous`,
  `methods: [GET, POST, HEAD]`
- Top comment block: "This file is the hackathon's Alibaba Cloud
  deployment proof" + the three deploy commands.

### 2. `bootstrap` (project root)
`#!/bin/bash` script (must be committed executable):
- `set -e`; `mkdir -p /tmp/runs`
- exec the layer python: `exec python3 -m uvicorn quotepilot.web.app:app --host 0.0.0.0 --port 9000`

### 3. `deploy/requirements.txt`
Runtime deps only (NO agentscope, NO dev tools):
openai, pydantic, httpx, jinja2, python-dotenv, fastapi, uvicorn,
python-multipart — with the same minimum versions as the project:
openai>=1.40, pydantic>=2.7, httpx>=0.27, jinja2>=3.1, python-dotenv>=1.0,
fastapi>=0.111, uvicorn>=0.30, python-multipart>=0.0.9

### 4. `deploy/package.sh`
Bash script that builds a clean `./.deploy_build/` staging dir:
- rsync/cp: `src/`, `templates/`, `data/`, `s.yaml`, `bootstrap`, `deploy/requirements.txt`
- run the vendored pip install (command above) into `.deploy_build/vendor`
- chmod +x bootstrap
- echo next steps (`cd .deploy_build && s deploy`)

### 5. `deploy/README.md`
Concise runbook:
1. Prereqs: Alibaba Cloud intl account, FC activated in ap-southeast-1,
   RAM user with `AliyunFCFullAccess` + AccessKey pair.
2. `npm install -g @serverless-devs/s` and `s config add` (choose Alibaba
   Cloud, paste AccessKeyID/Secret, alias `default`).
3. Look up the Python310 public layer ARN in the region and paste it into
   s.yaml.
4. `export QWEN_API_KEY=...` (from .env; never commit it).
5. `bash deploy/package.sh && cd .deploy_build && s deploy`.
6. Verify: `curl https://<assigned>.ap-southeast-1.fcapp.run/` and record the
   console + URL for the hackathon deployment-proof video.
7. Troubleshooting section: port must be 9000; check logs with `s logs -t`;
   wheels must be manylinux (rerun package.sh on failure); cold start ~2-4s.
