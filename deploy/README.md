# Deploying QuotePilot to Alibaba Cloud Function Compute (FC 3.0)

The dashboard runs as a **custom-runtime Web Function** in `ap-southeast-1`
(Singapore). `s.yaml` at the repo root is the hackathon's deployment-proof
file.

## One-time prerequisites (Alibaba Cloud console)

1. **Activate Function Compute**: console → Function Compute → activate the
   service (choose ap-southeast-1). New accounts get a monthly free tier.
2. **Create a RAM user + AccessKey**: console → RAM → Users → Create User →
   enable *OpenAPI access* → attach policy **AliyunFCFullAccess** → create an
   **AccessKey pair** and save the ID + Secret.
3. **Find the Python 3.10 public layer ARN**: Function Compute console →
   Layers → Public layers → Python310 → copy the ARN for ap-southeast-1, and
   paste it into `s.yaml` under `layers:`.

## One-time local setup

```bash
npm install -g @serverless-devs/s   # or --prefix ~/.local
s config add                        # vendor: Alibaba Cloud; paste AccessKey ID/Secret; alias: default
```

## Deploy

```bash
export QWEN_API_KEY=sk-...          # same key as .env — NEVER commit it
bash deploy/package.sh              # builds ./.deploy_build (src + vendored linux wheels)
cd .deploy_build && s deploy
s info                              # prints the public https://…fcapp.run URL
```

Open the URL — you should see the QuotePilot dashboard. Record the FC console
page + the URL for the hackathon's proof-of-deployment video.

## Troubleshooting

- **Import errors at cold start** → wheels not manylinux/cp310: rerun
  `deploy/package.sh` (it pins `--platform manylinux2014_x86_64
  --python-version 310 --only-binary=:all:`).
- **Connection refused / health-check fail** → server must bind
  `0.0.0.0:9000` (see `bootstrap`); port and `customRuntimeConfig.port` must
  match.
- **`python3: command not found` or wrong version** → the Python310 layer ARN
  is missing/wrong in `s.yaml`, or `/opt/python3.10/bin` is not first in the
  `PATH` env var (adjust to the layer's actual bin path shown on its console
  page).
- **Logs**: `s logs -t` (or FC console → function → Logs).
- **Runs disappear** → expected: /tmp is per-instance and ephemeral; the demo
  is designed around a single warm instance.
