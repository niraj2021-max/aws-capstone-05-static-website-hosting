"""
Automated Static Website Hosting Using AWS SDK (boto3)

Usage:
  python deploy_website.py --bucket YOUR-UNIQUE-BUCKET-NAME --region ap-south-1
  python deploy_website.py --bucket YOUR-UNIQUE-BUCKET-NAME --region ap-south-1 --source ./site --create-bucket

The script uploads files from the website folder and enables S3 website hosting.
Public website hosting requires a public-read bucket policy and account/bucket
Block Public Access settings that permit it. Prefer CloudFront + Origin Access
Control for production websites.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
import sys

import boto3
from botocore.exceptions import ClientError

DEFAULT_SITE_DIR = Path(__file__).parent / "site"


def bucket_exists(s3, bucket: str) -> bool:
    try:
        s3.head_bucket(Bucket=bucket)
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"404", "NoSuchBucket", "NotFound"} or status == 404:
            return False
        raise


def create_bucket(s3, bucket: str, region: str) -> None:
    args = {"Bucket": bucket}
    if region != "us-east-1":
        args["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**args)
    print(f"Created bucket: {bucket}")


def upload_folder(s3, bucket: str, source: Path) -> int:
    if not source.exists() or not source.is_dir():
        raise ValueError(f"Website folder does not exist: {source}")
    files = [f for f in source.rglob("*") if f.is_file()]
    if not files:
        raise ValueError(f"No files found in website folder: {source}")

    for file_path in files:
        key = file_path.relative_to(source).as_posix()
        content_type, _ = mimetypes.guess_type(str(file_path))
        extra_args = {"ContentType": content_type or "application/octet-stream"}
        # Ensure common web assets are served with correct MIME types.
        if file_path.suffix.lower() == ".js":
            extra_args["ContentType"] = "text/javascript"
        elif file_path.suffix.lower() == ".css":
            extra_args["ContentType"] = "text/css"
        s3.upload_file(str(file_path), bucket, key, ExtraArgs=extra_args)
        print(f"Uploaded: {key} ({extra_args['ContentType']})")
    return len(files)


def configure_website(s3, bucket: str) -> None:
    s3.put_bucket_website(
        Bucket=bucket,
        WebsiteConfiguration={
            "IndexDocument": {"Suffix": "index.html"},
            "ErrorDocument": {"Key": "error.html"},
        },
    )


def configure_public_read_for_demo(s3, bucket: str) -> None:
    """Public-read policy for a learning demo only; review your account settings."""
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "PublicReadForStaticWebsiteDemo",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{bucket}/*",
        }],
    }
    s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload and host a static website on Amazon S3.")
    parser.add_argument("--bucket", required=True, help="Globally unique S3 bucket name")
    parser.add_argument("--region", default="ap-south-1", help="AWS region (default: ap-south-1)")
    parser.add_argument("--source", default=str(DEFAULT_SITE_DIR), help="Website folder to upload")
    parser.add_argument("--create-bucket", action="store_true", help="Create the bucket if it does not exist")
    parser.add_argument("--public-read-demo", action="store_true",
                        help="Apply public-read bucket policy (learning/demo use only)")
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region)
    s3 = session.client("s3")
    try:
        exists = bucket_exists(s3, args.bucket)
        if not exists:
            if not args.create_bucket:
                print("Bucket does not exist. Re-run with --create-bucket after choosing a globally unique name.")
                return 2
            create_bucket(s3, args.bucket, args.region)

        count = upload_folder(s3, args.bucket, Path(args.source).resolve())
        configure_website(s3, args.bucket)
        if args.public_read_demo:
            configure_public_read_for_demo(s3, args.bucket)
            print("WARNING: Public-read policy applied. Ensure Block Public Access settings allow this.")
        endpoint = f"http://{args.bucket}.s3-website-{args.region}.amazonaws.com"
        if args.region == "us-east-1":
            endpoint = f"http://{args.bucket}.s3-website-us-east-1.amazonaws.com"
        print(f"\nDeployment configuration complete. Files uploaded: {count}")
        print(f"S3 website endpoint (HTTP): {endpoint}")
        print("Note: Website endpoint works only if public access is intentionally configured.")
        return 0
    except (ClientError, ValueError) as exc:
        print(f"Deployment failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
