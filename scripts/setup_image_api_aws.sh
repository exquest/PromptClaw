#!/bin/bash
# Provision the CypherClaw image-api AWS resources:
#   - S3 bucket  (us-west-2, public-read on jobs/*, CORS, 30-day lifecycle)
#   - IAM user   (cypherclaw-image-api, scoped to PutObject/GetObject/DeleteObject on jobs/*)
#   - Access key (printed once — copy it out, paste into Claude or a new profile)
#
# Run with admin AWS credentials. Idempotent: safe to re-run after partial failure.
#
# Usage:
#   ./scripts/setup_image_api_aws.sh                    # uses default AWS profile
#   ./scripts/setup_image_api_aws.sh --profile admin    # uses [admin] profile
#
# After this completes, the printed access key goes into cypherclaw's systemd
# env file so the image_api service can upload via boto3.

set -euo pipefail

BUCKET="ctmarketing-cypherclaw-images"
REGION="us-west-2"
IAM_USER="cypherclaw-image-api"
LIFECYCLE_DAYS=30

# Optional --profile passthrough
AWS_ARGS=()
if [ "${1:-}" = "--profile" ] && [ -n "${2:-}" ]; then
    AWS_ARGS+=(--profile "$2")
    echo ">>> using AWS profile: $2"
elif [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    head -16 "$0" | tail -15
    exit 0
fi

aws_cmd() { aws ${AWS_ARGS[@]+"${AWS_ARGS[@]}"} "$@"; }

echo ">>> AWS identity:"
aws_cmd sts get-caller-identity

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ----- Bucket --------------------------------------------------------------

if aws_cmd s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
    echo ">>> bucket $BUCKET already exists (you have access) — skipping create"
else
    HEAD_EXIT=$?
    # head-bucket returns non-zero for both "doesn't exist" and "exists but no access"
    # Try to create; AWS will tell us if it's globally claimed.
    echo ">>> creating bucket $BUCKET in $REGION"
    aws_cmd s3api create-bucket \
        --bucket "$BUCKET" \
        --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION"
fi

# ----- Public access (allow bucket policy, block ACLs) ---------------------

echo ">>> public access block: ACLs blocked, policy allowed"
aws_cmd s3api put-public-access-block --bucket "$BUCKET" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false"

# ----- Bucket policy: public read on jobs/* --------------------------------

cat > "$TMP/bucket-policy.json" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PublicReadJobsPrefix",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::$BUCKET/jobs/*"
  }]
}
EOF

echo ">>> bucket policy: public-read on jobs/*"
aws_cmd s3api put-bucket-policy --bucket "$BUCKET" --policy "file://$TMP/bucket-policy.json"

# ----- Lifecycle: expire jobs/* after 30 days ------------------------------

cat > "$TMP/lifecycle.json" <<EOF
{
  "Rules": [{
    "ID": "DeleteOldJobImages",
    "Status": "Enabled",
    "Filter": {"Prefix": "jobs/"},
    "Expiration": {"Days": $LIFECYCLE_DAYS}
  }]
}
EOF

echo ">>> lifecycle: jobs/* expires after $LIFECYCLE_DAYS days"
aws_cmd s3api put-bucket-lifecycle-configuration \
    --bucket "$BUCKET" \
    --lifecycle-configuration "file://$TMP/lifecycle.json"

# ----- CORS: GET/HEAD from any origin (CTMarketing browsers fetch direct) --

cat > "$TMP/cors.json" <<EOF
{
  "CORSRules": [{
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedOrigins": ["*"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3000
  }]
}
EOF

echo ">>> CORS: GET/HEAD any origin"
aws_cmd s3api put-bucket-cors --bucket "$BUCKET" --cors-configuration "file://$TMP/cors.json"

# ----- IAM user ------------------------------------------------------------

if aws_cmd iam get-user --user-name "$IAM_USER" >/dev/null 2>&1; then
    echo ">>> IAM user $IAM_USER already exists — skipping create"
else
    echo ">>> creating IAM user $IAM_USER"
    aws_cmd iam create-user --user-name "$IAM_USER" >/dev/null
fi

# Inline policy: PutObject/GetObject/DeleteObject on jobs/* only.
# Tight scope means a leaked key can't read/delete from other prefixes or buckets.
cat > "$TMP/user-policy.json" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
    "Resource": "arn:aws:s3:::$BUCKET/jobs/*"
  }]
}
EOF

echo ">>> inline policy on $IAM_USER: PutObject/GetObject/DeleteObject on jobs/*"
aws_cmd iam put-user-policy \
    --user-name "$IAM_USER" \
    --policy-name PutObjectsToImagesBucket \
    --policy-document "file://$TMP/user-policy.json"

# ----- Access key ----------------------------------------------------------

EXISTING_KEYS=$(aws_cmd iam list-access-keys --user-name "$IAM_USER" \
    --query 'AccessKeyMetadata[].AccessKeyId' --output text)

if [ -n "$EXISTING_KEYS" ]; then
    echo
    echo ">>> $IAM_USER already has access keys: $EXISTING_KEYS"
    echo "    Not creating a new one (AWS limits 2 keys per user)."
    echo "    To rotate:  aws iam delete-access-key --user-name $IAM_USER --access-key-id KEYID"
    echo "    Then re-run this script."
else
    echo ">>> creating access key for $IAM_USER"
    KEY_OUT=$(aws_cmd iam create-access-key --user-name "$IAM_USER")
    KEY_ID=$(echo "$KEY_OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKey']['AccessKeyId'])")
    KEY_SECRET=$(echo "$KEY_OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKey']['SecretAccessKey'])")

    echo
    echo "==============================================================="
    echo "  COPY THESE NOW. The secret will not be shown again."
    echo "==============================================================="
    echo "  AWS_ACCESS_KEY_ID=$KEY_ID"
    echo "  AWS_SECRET_ACCESS_KEY=$KEY_SECRET"
    echo "==============================================================="
fi

echo
echo ">>> SETUP COMPLETE."
echo "    Bucket:  s3://$BUCKET  ($REGION)"
echo "    URL fmt: https://$BUCKET.s3.$REGION.amazonaws.com/jobs/{job_id}/{file}"
echo "    IAM:     $IAM_USER  (scoped to jobs/* PutObject/GetObject/DeleteObject)"
echo
echo "    Verify:  aws s3api head-bucket --bucket $BUCKET"
echo "    Verify:  aws iam list-access-keys --user-name $IAM_USER"
