"""Failure-safe evidence files: a previous success must not survive a new failed run."""
import json
from pathlib import Path


def write_result(path,result):
    path=Path(path);temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,indent=2),encoding='utf-8');temporary.replace(path)


def begin_run(path,policy):
    result={'policy':policy,'success':False,'status':'running','events':[]}
    write_result(path,result);return result


def safe_manifest(client):
    if client is None:return None
    try:return client.request({'type':'manifest'})['model']
    except Exception as error:return {'unavailable':str(error)}
