import os
import tempfile

import torch
import torchaudio
from rq import Queue, SimpleWorker

from src.config import S3_RESULTS_BUCKET
from src.connections import _database_session, _redis_connection
from src.database.orm import UsageHistory
from src.file_storages import s3
from src.models.enhancer import EnhancerModel

LISTEN_KEYS = ["default"]


def process_audio_enhancement(s3_object_key, task_id=None):
    """
    Process audio file with enhancer model

    Args:
        s3_object_key: S3 object key of the uploaded audio file
        task_id: ID of the task in history

    Returns:
        result_s3_key: S3 object key of the processed audio file
    """
    ENHANCER_MODEL = EnhancerModel(device="cuda" if torch.cuda.is_available() else "cpu")
    with _database_session() as db:
        try:
            redis_conn = _redis_connection()
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_input_path = os.path.join(temp_dir, f"input{os.path.splitext(s3_object_key)[1]}")
                s3.download_file(s3_object_key, temp_input_path)

                db.query(UsageHistory).filter(UsageHistory.id == task_id).update({"status": "processing"})
                db.commit()

                audio, sample_rate = torchaudio.load(temp_input_path)

                enhanced_audio, new_sample_rate = ENHANCER_MODEL.enhance_audio(audio, sample_rate)

                temp_output_path = os.path.join(temp_dir, f"output{os.path.splitext(s3_object_key)[1]}")
                torchaudio.save(temp_output_path, enhanced_audio, new_sample_rate)

                result_s3_key = s3.upload_file(temp_output_path, bucket=S3_RESULTS_BUCKET)

                result_url = s3.generate_presigned_url(result_s3_key, bucket=S3_RESULTS_BUCKET)

                if task_id:
                    redis_conn.set(f"task:{task_id}:result_s3_key", result_s3_key)
                    redis_conn.set(f"task:{task_id}:result_url", result_url)
                    redis_conn.expire(f"task:{task_id}:result_s3_key", 24 * 60 * 60)
                    redis_conn.expire(f"task:{task_id}:result_url", 24 * 60 * 60)

                db.query(UsageHistory).filter(UsageHistory.id == task_id).update({"status": "completed"})
                db.commit()

            return {"result_s3_key": result_s3_key, "result_url": result_url}
        except Exception as e:
            db.query(UsageHistory).filter(UsageHistory.id == task_id).update({"status": "failed"})
            db.commit()
            raise e


if __name__ == "__main__":
    redis_conn = _redis_connection()

    with redis_conn.client() as connection:
        worker = SimpleWorker([Queue(connection=redis_conn)], connection=redis_conn)
        worker.work()
