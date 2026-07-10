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

- **Import errors at cold start** → wheels not manylinux/cp311: rerun
  `deploy/package.sh` (it pins `--platform manylinux2014_x86_64
  --python-version 311 --only-binary=:all:` — matches the `custom.debian12`
  image's system Python 3.11.2; `custom.debian10`'s docs-promised Python 3.10
  does NOT exist in ap-southeast-1, we verified the image only has 3.7).
- **Connection refused / health-check fail** → server must bind
  `0.0.0.0:9000` (see `bootstrap`); port and `customRuntimeConfig.port` must
  match.
- **3xx responses fail with `ExternalRedirectForbidden`** → the fcapp.run
  system domain forbids HTTP redirects; the app therefore uses meta-refresh
  pages instead of 303s (see `_goto()` in `web/app.py`). Keep it that way
  unless you attach a custom domain.
- **Logs**: `s logs -t` (or FC console → function → Logs).
- **Runs disappear** → expected: /tmp is per-instance and ephemeral; the demo
  is designed around a single warm instance.
