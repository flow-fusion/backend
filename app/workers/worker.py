"""Main worker entry point for processing events."""

import argparse
import signal
import sys
import time
from typing import Optional
from rq import Queue, Worker as RQWorker, Connection
from rq.job import Job
from rq.registry import FailedJobRegistry
import redis

from app.core.config import get_settings
from app.core.logging_config import setup_logging, get_logger
from app.core.database import init_db
from app.processing.event_processor import EventProcessor
from app.processing.event_queue_service import EventQueueService

# Setup logging
logger = get_logger("worker")


class Worker:
    """
    Main worker class for processing events.
    
    Supports both RQ-based and direct processing modes.
    """

    def __init__(self, use_rq: bool = True):
        settings = get_settings()
        self.use_rq = use_rq
        self.settings = settings
        self.event_processor: Optional[EventProcessor] = None
        self.queue_service: Optional[EventQueueService] = None
        self._running = False
        self._shutdown_requested = False

    def initialize(self) -> None:
        """Initialize worker components."""
        logger.info("Initializing worker...")
        
        # Initialize database
        init_db()
        logger.info("Database initialized")
        
        # Initialize processing components
        self.queue_service = EventQueueService()
        self.event_processor = EventProcessor(queue_service=self.queue_service)
        
        logger.info("Worker initialized successfully")

    def start(self) -> None:
        """Start the worker."""
        self.initialize()
        self._running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        logger.info("Worker started")
        
        if self.use_rq:
            self._run_rq_worker()
        else:
            self._run_direct_worker()

    def _run_rq_worker(self) -> None:
        """Run using RQ (Redis Queue) for job management."""
        settings = get_settings()
        
        redis_conn = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
        )
        
        # Create queues
        main_queue = Queue(settings.EVENT_QUEUE_NAME, connection=redis_conn)
        retry_queue = Queue(settings.EVENT_RETRY_QUEUE_NAME, connection=redis_conn)
        
        logger.info(f"RQ worker listening on queues: {settings.EVENT_QUEUE_NAME}, {settings.EVENT_RETRY_QUEUE_NAME}")
        
        # Create RQ worker
        rq_worker = RQWorker(
            [main_queue, retry_queue],
            connection=redis_conn,
            log_job_description=True,
        )
        
        # Work with exception handling
        while self._running and not self._shutdown_requested:
            try:
                # Process scheduled retries
                self.queue_service.process_scheduled_retries()
                
                # Work for a limited time to allow shutdown checks
                rq_worker.work(burst=False, with_scheduler=True, max_idle_time=30)
                
            except Exception as e:
                logger.exception(f"RQ worker error: {str(e)}")
                time.sleep(5)

    def _run_direct_worker(self) -> None:
        """Run using direct Redis queue polling (simpler, no RQ)."""
        logger.info("Starting direct queue polling worker")
        
        while self._running and not self._shutdown_requested:
            try:
                # Process scheduled retries
                self.queue_service.process_scheduled_retries()
                
                # Process events from queue
                self.event_processor.run_worker(poll_timeout=5)
                
            except Exception as e:
                logger.exception(f"Direct worker error: {str(e)}")
                time.sleep(5)

    def _handle_shutdown(self, signum, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Shutdown signal received ({signum})")
        self._shutdown_requested = True
        self._running = False

    def stop(self) -> None:
        """Stop the worker."""
        logger.info("Stopping worker...")
        self._running = False


def process_event_job(event_id: int) -> bool:
    """
    RQ job function to process a single event.
    
    This function is called by RQ workers.
    
    Args:
        event_id: The database ID of the event to process.
        
    Returns:
        True if processing succeeded.
    """
    # Setup logging for this job
    setup_logging()
    job_logger = get_logger("rq_job")
    
    job_logger.info(f"Processing event {event_id} (RQ job)")
    
    try:
        processor = EventProcessor()
        success = processor.process_event(event_id)
        
        if success:
            job_logger.info(f"Event {event_id} processed successfully")
        else:
            job_logger.warning(f"Event {event_id} processing returned False")
        
        return success
        
    except Exception as e:
        job_logger.exception(f"Error processing event {event_id}: {str(e)}")
        raise  # Re-raise for RQ to handle as failed job


def enqueue_event(event_id: int) -> str:
    """
    Enqueue an event for processing.
    
    This function is called by the webhook layer to queue events.
    
    Args:
        event_id: The database ID of the event to process.
        
    Returns:
        Job ID string.
    """
    settings = get_settings()
    
    redis_conn = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
    )
    
    with Connection(redis_conn):
        queue = Queue(settings.EVENT_QUEUE_NAME)
        job = queue.enqueue(process_event_job, event_id)
    
    logger.info(f"Enqueued event {event_id} as job {job.id}")
    return job.id


def run_worker() -> None:
    """Main entry point for running the worker."""
    parser = argparse.ArgumentParser(description="AI Concurs Event Processor Worker")
    parser.add_argument(
        "--use-rq",
        action="store_true",
        default=True,
        help="Use RQ for job management (default: True)",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Use direct queue polling instead of RQ",
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    # Create and start worker
    use_rq = args.use_rq and not args.direct
    worker = Worker(use_rq=use_rq)
    
    try:
        worker.start()
    except KeyboardInterrupt:
        logger.info("Worker interrupted")
    finally:
        worker.stop()


if __name__ == "__main__":
    run_worker()
