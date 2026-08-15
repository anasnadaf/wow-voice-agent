# Runbook — WOW voice-agent host

One EC2 m7i-flex.large (`ap-south-1`), its own nginx ingress, Cloudflare in
front of `wow.anasnadaf.com` (app) and `wowlogs.anasnadaf.com` (MLflow).
Ports 80/443 admit Cloudflare ranges only; shell access is SSM, not SSH.

## Provision

```bash
cd deploy && ./provision-ec2.sh        # idempotent; prints instance id + EIP
```

Then in Cloudflare DNS (anasnadaf.com): `A wow → <EIP>` and `A wowlogs → <EIP>`,
both proxied, SSL mode **Full (strict)**. If voice websocket latency through the
proxy ever becomes a problem, flip `wow` to DNS-only — the SG must then also
open 443 to the world, so prefer keeping the proxy.

## First deploy

```bash
aws ssm start-session --region ap-south-1 --target <instance-id>
sudo git clone https://github.com/anasnadaf/wow-voice-agent /opt/wow-voice-agent
cd /opt/wow-voice-agent/deploy
sudo cp .env.example .env && sudo vi .env          # secrets; ${VAR:?} enforces
# place certs/origin.pem, certs/origin-key.pem, certs/htpasswd (see certs/README.md)
sudo docker compose -f compose.prod.yml up -d
curl -s https://wow.anasnadaf.com/healthz
```

## Deploys

Images are built by CI on every push to main (`ghcr.io/anasnadaf/wow-voice-agent-server`
/`-web`, tags `latest` + SHA). The `deploy.yml` workflow then tells the host to
pull and restart over SSM — nothing manual. To deploy by hand:

```bash
aws ssm send-command --region ap-south-1 \
  --document-name AWS-RunShellScript \
  --targets Key=tag:Name,Values=wow-voice-agent \
  --parameters 'commands=["cd /opt/wow-voice-agent && git pull && cd deploy && docker compose -f compose.prod.yml pull && docker compose -f compose.prod.yml up -d"]'
```

## Rollback

Pin the previous SHA in `.env` and re-run compose:

```
SERVER_IMAGE=ghcr.io/anasnadaf/wow-voice-agent-server:<sha>
```

## Config-only nginx changes

```bash
docker compose -f compose.prod.yml exec proxy nginx -t \
  && docker compose -f compose.prod.yml restart proxy
```

`nginx -t` first, always — this is the only ingress.

## Debugging

```bash
docker compose -f compose.prod.yml ps
docker compose -f compose.prod.yml logs -f server   # pipeline + call logs
docker compose -f compose.prod.yml logs proxy       # 4xx/5xx at the edge
```

- MLflow answers 400 through the proxy → its `--allowed-hosts` doesn't list
  the public hostname (`MLFLOW_ALLOWED_HOSTS` in `.env`).
- Runs appear but artifacts (transcript, recording) are missing → MLflow must
  run with `--serve-artifacts --artifacts-destination`, never a local
  `--default-artifact-root`: the server container's filesystem is not writable
  by the app container, and the failure is a log warning, not an error. Note
  that an experiment stores its artifact location at creation time, so fixing
  the flag does not repair an experiment created under the old config —
  create a new one (or `mlflow gc` the old).
- Plivo can't reach the websocket → check Cloudflare proxied status and that
  `/ws/` upgrade headers survive (`curl -i -H 'Upgrade: websocket' ...`).
- Recordings live in the `recordings` volume (`/data/recordings` in server).
