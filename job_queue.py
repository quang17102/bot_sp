# -*- coding: utf-8 -*-
"""
Job Queue System cho Bot Telegram
X\u1EED l\u00FD c\u00E1c job b\u1EA5t \u0111\u1ED3ng b\u1ED9 v\u1EDBi Worker pattern
"""

import queue
import threading
import time
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class Job:
    """Class \u0111\u1EA1i di\u1EC7n cho m\u1ED9t job"""
    job_id: str
    job_type: str
    user_id: int
    chat_id: int
    data: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"  # pending, processing, completed, failed
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class JobQueue:
    """Job Queue Manager"""
    
    def __init__(self, max_workers: int = 3):
        self.job_queue = queue.Queue()
        self.jobs: Dict[str, Job] = {}
        self.max_workers = max_workers
        self.workers: list[threading.Thread] = []
        self.handlers: Dict[str, Callable] = {}
        self.running = False
        self.lock = threading.Lock()
        self.bot_app = None  # Bot application instance \u0111\u1EC3 workers g\u1EEDi message
        self.cleanup_thread = None  # Thread cho cleanup task
    
    def set_bot_app(self, bot_app):
        """Set bot application instance \u0111\u1EC3 workers c\u00F3 th\u1EC3 g\u1EEDi message"""
        self.bot_app = bot_app
        
    def register_handler(self, job_type: str, handler: Callable):
        """\u0110\u0103ng k\u00FD handler cho m\u1ED9t lo\u1EA1i job"""
        self.handlers[job_type] = handler
        
    def add_job(self, job_type: str, user_id: int, chat_id: int, data: Dict[str, Any]) -> str:
        """Th\u00EAm job v\u00E0o queue"""
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            job_type=job_type,
            user_id=user_id,
            chat_id=chat_id,
            data=data
        )
        
        with self.lock:
            self.jobs[job_id] = job
        
        self.job_queue.put(job)
        return job_id
    
    def add_job_if_no_active(self, job_type: str, user_id: int, chat_id: int, data: Dict[str, Any]) -> Optional[str]:
        """
        Th\u00EAm job CH\u1EC8 KHI user kh\u00F4ng c\u00F3 job \u0111ang ch\u1EA1y
        Atomic operation: Check + Create trong c\u00F9ng lock \u0111\u1EC3 tr\u00E1nh race condition
        
        Args:
            job_type: Lo\u1EA1i job
            user_id: ID c\u1EE7a user
            chat_id: ID c\u1EE7a chat
            data: D\u1EEF li\u1EC7u c\u1EE7a job
        
        Returns:
            job_id n\u1EBFu t\u1EA1o th\u00E0nh c\u00F4ng, None n\u1EBFu user \u0111\u00E3 c\u00F3 job \u0111ang ch\u1EA1y
        """
        with self.lock:  # Lock cho to\u00E0n b\u1ED9 operation (atomic)
            # B\u01AF\u1EDAC 1: Check (trong lock)
            for job in self.jobs.values():
                if job.user_id == user_id:
                    if job_type is None or job.job_type == job_type:
                        if job.status in ["pending", "processing"]:
                            return None  # \u0110\u00E3 c\u00F3 job \u0111ang ch\u1EA1y \u2192 Return None (ch\u1EB7n)
            
            # B\u01AF\u1EDAC 2: Create (c\u00F9ng trong lock - kh\u00F4ng c\u00F3 gap!)
            job_id = str(uuid.uuid4())
            job = Job(
                job_id=job_id,
                job_type=job_type,
                user_id=user_id,
                chat_id=chat_id,
                data=data
            )
            self.jobs[job_id] = job
            self.job_queue.put(job)
            return job_id
        # Lock ch\u1EC9 release khi TO\u00C0N B\u1ED8 function return
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """L\u1EA5y job theo ID"""
        with self.lock:
            return self.jobs.get(job_id)
    
    def update_job_status(self, job_id: str, status: str, result: Optional[Dict] = None, error: Optional[str] = None):
        """C\u1EADp nh\u1EADt tr\u1EA1ng th\u00E1i job"""
        with self.lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.status = status
                if result:
                    job.result = result
                if error:
                    job.error = error
    
    def worker_loop(self, worker_id: int):
        """V\u00F2ng l\u1EB7p x\u1EED l\u00FD job c\u1EE7a worker"""
        print(f"Worker {worker_id} started")
        while self.running:
            try:
                # L\u1EA5y job t\u1EEB queue (timeout 1 gi\u00E2y \u0111\u1EC3 c\u00F3 th\u1EC3 check self.running)
                try:
                    job = self.job_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # Ki\u1EC3m tra handler
                if job.job_type not in self.handlers:
                    self.update_job_status(job.job_id, "failed", error=f"Kh\u00F4ng t\u00ECm th\u1EA5y handler cho job type: {job.job_type}")
                    self.job_queue.task_done()
                    continue
                
                # C\u1EADp nh\u1EADt tr\u1EA1ng th\u00E1i
                self.update_job_status(job.job_id, "processing")
                
                # X\u1EED l\u00FD job
                try:
                    handler = self.handlers[job.job_type]
                    result = handler(job)
                    self.update_job_status(job.job_id, "completed", result=result)
                except Exception as e:
                    error_msg = str(e)
                    print(f"Worker {worker_id} error processing job {job.job_id}: {error_msg}")
                    self.update_job_status(job.job_id, "failed", error=error_msg)
                
                self.job_queue.task_done()
                
            except Exception as e:
                print(f"Worker {worker_id} exception: {e}")
                time.sleep(1)
        
        print(f"Worker {worker_id} stopped")
    
    def cleanup_old_jobs(self, max_age_seconds: int = 300):
        """
        X\u00F3a jobs c\u0169 \u0111\u00E3 completed/failed
        
        Args:
            max_age_seconds: Th\u1EDDi gian t\u1ED1i \u0111a gi\u1EEF jobs c\u0169 (m\u1EB7c \u0111\u1ECBnh 5 ph\u00FAt = 300s)
        
        Returns:
            S\u1ED1 l\u01B0\u1EE3ng jobs \u0111\u00E3 x\u00F3a
        """
        import time
        now = time.time()
        with self.lock:
            to_remove = []
            for job_id, job in self.jobs.items():
                if job.status in ["completed", "failed"]:
                    age = (now - job.created_at.timestamp())
                    if age > max_age_seconds:
                        to_remove.append(job_id)
            
            for job_id in to_remove:
                del self.jobs[job_id]
            
            if to_remove:
                print(f"Cleaned up {len(to_remove)} old jobs (kept {len(self.jobs)} jobs)")
        
        return len(to_remove)
    
    def start_cleanup_task(self, interval_seconds: int = 60, max_age_seconds: int = 300):
        """
        B\u1EAFt \u0111\u1EA7u task cleanup \u0111\u1ECBnh k\u1EF3
        
        Args:
            interval_seconds: Kho\u1EA3ng th\u1EDDi gian gi\u1EEFa c\u00E1c l\u1EA7n cleanup (m\u1EB7c \u0111\u1ECBnh 60s)
            max_age_seconds: Th\u1EDDi gian t\u1ED1i \u0111a gi\u1EEF jobs c\u0169 (m\u1EB7c \u0111\u1ECBnh 300s = 5 ph\u00FAt)
        """
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            return  # \u0110\u00E3 ch\u1EA1y r\u1ED3i
        
        def cleanup_loop():
            """V\u00F2ng l\u1EB7p cleanup \u0111\u1ECBnh k\u1EF3"""
            print(f"Cleanup task started (interval: {interval_seconds}s, max_age: {max_age_seconds}s)")
            while self.running:
                try:
                    time.sleep(interval_seconds)
                    if self.running:
                        self.cleanup_old_jobs(max_age_seconds)
                except Exception as e:
                    print(f"Cleanup task error: {e}")
                    time.sleep(interval_seconds)
        
        self.cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        print("Cleanup task started")
    
    def start_workers(self):
        """Kh\u1EDFi \u0111\u1ED9ng c\u00E1c worker"""
        if self.running:
            return
        
        self.running = True
        for i in range(self.max_workers):
            worker = threading.Thread(target=self.worker_loop, args=(i+1,), daemon=True)
            worker.start()
            self.workers.append(worker)
        print(f"Started {self.max_workers} workers")
        
        # B\u1EAFt \u0111\u1EA7u cleanup task
        self.start_cleanup_task()
    
    def stop_workers(self):
        """D\u1EEBng c\u00E1c worker"""
        self.running = False
        # \u0110\u1EE3i t\u1EA5t c\u1EA3 job ho\u00E0n th\u00E0nh
        self.job_queue.join()
        print("All workers stopped")
    
    def get_queue_size(self) -> int:
        """L\u1EA5y s\u1ED1 l\u01B0\u1EE3ng job \u0111ang ch\u1EDD"""
        return self.job_queue.qsize()
    
    def get_active_jobs_count(self) -> int:
        """L\u1EA5y s\u1ED1 l\u01B0\u1EE3ng job \u0111ang x\u1EED l\u00FD"""
        with self.lock:
            return sum(1 for job in self.jobs.values() if job.status == "processing")
    
    def has_active_job_for_user(self, user_id: int, job_type: str = None) -> bool:
        """
        Ki\u1EC3m tra xem user c\u00F3 job \u0111ang x\u1EED l\u00FD kh\u00F4ng
        
        Args:
            user_id: ID c\u1EE7a user
            job_type: Lo\u1EA1i job c\u1EA7n ki\u1EC3m tra (None = ki\u1EC3m tra t\u1EA5t c\u1EA3 lo\u1EA1i)
        
        Returns:
            True n\u1EBFu user c\u00F3 job \u0111ang pending ho\u1EB7c processing
        """
        with self.lock:
            for job in self.jobs.values():
                if job.user_id == user_id:
                    if job_type is None or job.job_type == job_type:
                        if job.status in ["pending", "processing"]:
                            return True
        return False
    
    def get_active_job_for_user(self, user_id: int, job_type: str = None) -> Optional[Job]:
        """
        L\u1EA5y job \u0111ang ch\u1EA1y c\u1EE7a user
        
        Args:
            user_id: ID c\u1EE7a user
            job_type: Lo\u1EA1i job c\u1EA7n l\u1EA5y (None = l\u1EA5y b\u1EA5t k\u1EF3 lo\u1EA1i n\u00E0o)
        
        Returns:
            Job \u0111ang pending ho\u1EB7c processing, None n\u1EBFu kh\u00F4ng c\u00F3
        """
        with self.lock:
            for job in self.jobs.values():
                if job.user_id == user_id:
                    if job_type is None or job.job_type == job_type:
                        if job.status in ["pending", "processing"]:
                            return job
        return None

