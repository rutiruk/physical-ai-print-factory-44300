"""Asynchronous JSON-lines model subprocess. Simulation never waits on request()."""
import json
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]


class JsonWorker:
    def __init__(self,environment,script,log_path,args=()):
        path=ROOT/log_path;path.parent.mkdir(parents=True,exist_ok=True)
        self.log=path.open('w',encoding='utf-8');self.messages=Queue();self.busy=False
        self.process=subprocess.Popen([str(ROOT/environment/'Scripts/python.exe'),'-u',str(ROOT/'scripts'/script),*args],
            cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,encoding='utf-8',errors='replace',bufsize=1)
        def read():
            for line in self.process.stdout:
                self.log.write(line);self.log.flush()
                try:
                    item=json.loads(line)
                    if isinstance(item,dict):self.messages.put(item)
                except json.JSONDecodeError:pass
            self.messages.put({'error':f'{script} exited: {self.process.poll()}'})
        self.reader=Thread(target=read,daemon=True);self.reader.start()
        self.ready=self.messages.get(timeout=300)
        if not (self.ready.get('ready') or self.ready.get('status')=='ready'):raise RuntimeError(self.ready)

    def submit(self,payload):
        if self.busy:raise RuntimeError('Only one in-flight inference per worker')
        self.process.stdin.write(json.dumps(payload,ensure_ascii=True)+'\n');self.process.stdin.flush()
        self.busy=True;self.started=time.perf_counter()

    def poll(self):
        try:result=self.messages.get_nowait()
        except Empty:
            if self.busy and time.perf_counter()-self.started>180:raise TimeoutError('Model inference timed out')
            return None
        self.busy=False
        if 'error' in result:raise RuntimeError(result['error'])
        return result

    def request(self,payload):
        self.submit(payload)
        result=self.messages.get(timeout=180);self.busy=False
        if 'error' in result:raise RuntimeError(result['error'])
        return result

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.close();self.process.wait(timeout=15)
            except (BrokenPipeError,subprocess.TimeoutExpired):
                self.process.terminate();self.process.wait(timeout=5)
        self.reader.join(timeout=5)
        if not self.reader.is_alive():self.log.close()
