#!/usr/bin/env bash
# Provision the WOW voice-agent host: one m7i-flex.large behind Cloudflare.
#
# Idempotence: safe to re-run; each step skips resources that already exist
# (matched by name/tag). Requires: aws cli v2 with credentials, curl, jq.
#
#   ./provision-ec2.sh            # provision everything, print the EIP
#   REGION=ap-south-1 ./provision-ec2.sh
set -euo pipefail

REGION="${REGION:-ap-south-1}"
NAME="${NAME:-wow-voice-agent}"
INSTANCE_TYPE="${INSTANCE_TYPE:-m7i-flex.large}"

aws() { command aws --region "$REGION" "$@"; }

# ── security group: 80/443 from Cloudflare ranges only ───────────────────
VPC_ID=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true \
  --query 'Vpcs[0].VpcId' --output text)

SG_ID=$(aws ec2 describe-security-groups \
  --filters Name=group-name,Values="$NAME" Name=vpc-id,Values="$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$NAME" \
    --description "WOW voice agent - ingress from Cloudflare only" \
    --vpc-id "$VPC_ID" --query 'GroupId' --output text)
  echo "created security group $SG_ID"
  for cidr in $(curl -fsS https://www.cloudflare.com/ips-v4); do
    for port in 80 443; do
      aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
        --protocol tcp --port "$port" --cidr "$cidr" >/dev/null
    done
  done
  echo "authorized Cloudflare IPv4 ranges on 80/443"

  # WebRTC media for the browser demo. Signalling goes through Cloudflare, but
  # the audio itself is UDP straight from the visitor's browser to this host on
  # a port aiortc picks per call — so it cannot be narrowed to Cloudflare, and
  # the range has to be wide. Media is DTLS-SRTP encrypted and ignored unless it
  # matches a negotiated session. Drop this rule if you retire the browser demo.
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
    --protocol udp --port 10000-65535 --cidr 0.0.0.0/0 >/dev/null
  echo "authorized UDP 10000-65535 for WebRTC media"
else
  echo "security group exists: $SG_ID"
fi

# ── IAM: SSM access instead of SSH ───────────────────────────────────────
ROLE="$NAME-role"
if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"},
                   "Action": "sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$ROLE" \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws iam create-instance-profile --instance-profile-name "$ROLE" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
  echo "created IAM role + instance profile $ROLE (SSM)"
  sleep 10  # instance-profile propagation
else
  echo "IAM role exists: $ROLE"
fi

# ── instance ─────────────────────────────────────────────────────────────
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters Name=tag:Name,Values="$NAME" Name=instance-state-name,Values=pending,running \
  --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null || true)

if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
  AMI_ID=$(aws ssm get-parameter \
    --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
    --query 'Parameter.Value' --output text)
  INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" --instance-type "$INSTANCE_TYPE" \
    --security-group-ids "$SG_ID" \
    --iam-instance-profile Name="$ROLE" \
    --user-data file://"$(dirname "$0")"/user-data.sh \
    --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":40,"VolumeType":"gp3"}}]' \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
    --query 'Instances[0].InstanceId' --output text)
  echo "launched $INSTANCE_ID ($INSTANCE_TYPE)"
else
  echo "instance exists: $INSTANCE_ID"
fi

aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# ── elastic IP ───────────────────────────────────────────────────────────
ALLOC_ID=$(aws ec2 describe-addresses --filters Name=tag:Name,Values="$NAME" \
  --query 'Addresses[0].AllocationId' --output text 2>/dev/null || true)
if [ "$ALLOC_ID" = "None" ] || [ -z "$ALLOC_ID" ]; then
  ALLOC_ID=$(aws ec2 allocate-address --domain vpc \
    --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME}]" \
    --query 'AllocationId' --output text)
  echo "allocated EIP $ALLOC_ID"
fi
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" >/dev/null

EIP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" \
  --query 'Addresses[0].PublicIp' --output text)

cat <<EOF

done.
  instance : $INSTANCE_ID  ($INSTANCE_TYPE, $REGION)
  eip      : $EIP

next:
  1. Cloudflare DNS: A wow.anasnadaf.com -> $EIP (proxied)
                     A wowlogs.anasnadaf.com -> $EIP (proxied)
  2. Wait ~2 min for user-data, then finish setup over SSM:
       aws ssm start-session --region $REGION --target $INSTANCE_ID
     (clone repo into /opt, fill deploy/.env, place certs/, compose up)
     See deploy/runbook.md.
EOF
