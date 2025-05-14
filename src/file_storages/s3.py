import io
import logging
import uuid

import boto3
from botocore.exceptions import ClientError

from src import config

logger = logging.getLogger(__name__)


def get_s3_client():
    s3_client = boto3.client(
        "s3",
        endpoint_url=f"http://{config.S3_HOST}:{config.S3_PORT}",
        aws_access_key_id=config.S3_ACCESS_KEY,
        aws_secret_access_key=config.S3_SECRET_KEY,
        region_name=config.S3_REGION,
        config=boto3.session.Config(signature_version="s3v4"),
    )
    assert s3_client.list_buckets()
    return s3_client


def upload_fileobj(file_data, original_filename=None, content_type=None, bucket=None):
    """
    Upload a file-like object to S3

    Args:
        file_data: File-like object to upload
        original_filename: Original filename (optional)
        content_type: MIME type of the file (optional)
        bucket: S3 bucket name, defaults to uploads bucket

    Returns:
        object_name: The name of the object in S3
    """
    if bucket is None:
        bucket = config.S3_UPLOADS_BUCKET

    # Generate a unique filename
    ext = ""
    if original_filename:
        ext = original_filename.split(".")[-1] if "." in original_filename else ""
        ext = f".{ext}" if ext else ""

    object_name = f"{uuid.uuid4()}{ext}"

    s3_client = get_s3_client()

    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    try:
        s3_client.upload_fileobj(file_data, bucket, object_name, ExtraArgs=extra_args)
        logger.info(f"File uploaded successfully to {bucket}/{object_name}")
        return object_name
    except ClientError as e:
        logger.error(f"Error uploading file to S3: {e}")
        raise


def upload_file(file_path, bucket=None):
    """
    Upload a file from disk to S3

    Args:
        file_path: Path to the file to upload
        bucket: S3 bucket name, defaults to uploads bucket

    Returns:
        object_name: The name of the object in S3
    """
    if bucket is None:
        bucket = config.S3_UPLOADS_BUCKET

    # Generate a unique filename
    filename = file_path.split("/")[-1]
    ext = filename.split(".")[-1] if "." in filename else ""
    ext = f".{ext}" if ext else ""

    object_name = f"{uuid.uuid4()}{ext}"

    s3_client = get_s3_client()

    try:
        s3_client.upload_file(file_path, bucket, object_name)
        logger.info(f"File uploaded successfully to {bucket}/{object_name}")
        return object_name
    except ClientError as e:
        logger.error(f"Error uploading file to S3: {e}")
        raise


def download_fileobj(object_name, bucket=None):
    """
    Download a file from S3 to a bytes buffer

    Args:
        object_name: Name of the object in S3
        bucket: S3 bucket name, defaults to uploads bucket

    Returns:
        bytes_buffer: BytesIO containing the file data
    """
    if bucket is None:
        bucket = config.S3_UPLOADS_BUCKET

    bytes_buffer = io.BytesIO()
    s3_client = get_s3_client()

    try:
        s3_client.download_fileobj(bucket, object_name, bytes_buffer)
        bytes_buffer.seek(0)
        return bytes_buffer
    except ClientError as e:
        logger.error(f"Error downloading file from S3: {e}")
        raise


def download_file(object_name, file_path, bucket=None):
    """
    Download a file from S3 to disk

    Args:
        object_name: Name of the object in S3
        file_path: Path where the file should be saved
        bucket: S3 bucket name, defaults to uploads bucket
    """
    if bucket is None:
        bucket = config.S3_UPLOADS_BUCKET

    s3_client = get_s3_client()

    try:
        s3_client.download_file(bucket, object_name, file_path)
        logger.info(f"File downloaded successfully from {bucket}/{object_name} to {file_path}")
    except ClientError as e:
        logger.error(f"Error downloading file from S3: {e}")
        raise


def generate_presigned_url(object_name, bucket=None, expiration=3600):
    """
    Generate a presigned URL for an object

    Args:
        object_name: Name of the object in S3
        bucket: S3 bucket name, defaults to results bucket
        expiration: Time in seconds for the URL to remain valid

    Returns:
        presigned_url: The presigned URL
    """
    if bucket is None:
        bucket = config.S3_RESULTS_BUCKET

    s3_client = get_s3_client()

    try:
        presigned_url = s3_client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": object_name}, ExpiresIn=expiration
        )
        return presigned_url
    except ClientError as e:
        logger.error(f"Error generating presigned URL: {e}")
        raise
