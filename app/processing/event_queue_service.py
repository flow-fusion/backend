"""Event Queue Service for Redis queue operations."""

import json
import redis
from typing import Optional
from app.shared.config import get_settings
from app.shared.logging_config import get_logger

logger = get_logger("event_queue_service")


class EventQueueService:
    """
    Service for managing event queues in Redis.
    
    Responsible for:
    - Pushing event IDs to the processing queue
    - Managing retry and dead letter queues
    - Queue health monitoring
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        settings = get_settings()
        
        if redis_client is None:
            self.redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
            )
        else:
            self.redis = redis_client

        self.queue_name = settings.EVENT_QUEUE_NAME
        self.retry_queue_name = settings.EVENT_RETRY_QUEUE_NAME
        self.dead_letter_queue_name = settings.EVENT_DEAD_LETTER_QUEUE_NAME
        self.processing_key = f"{self.queue_name}:processing"  # Set of currently processing events
        self.processed_key = f"{self.queue_name}:processed"  # Set of processed event IDs (for dedup)

    def push_event(self, event_id: int) -> bool:
        """
        Push an event ID to the processing queue.
        
        Args:
            event_id: The database ID of the event to process.
            
        Returns:
            True if event was pushed, False if already in queue/processed.
        """
        # Check if already processed (deduplication)
        if self.is_event_processed(event_id):
            logger.debug(f"Event {event_id} already processed, skipping")
            return False

        # Check if already in queue
        if self.is_event_in_queue(event_id):
            logger.debug(f"Event {event_id} already in queue, skipping")
            return False

        self.redis.rpush(self.queue_name, str(event_id))
        logger.info(f"Pushed event {event_id} to queue '{self.queue_name}'")
        return True

    def pop_event(self, timeout: int = 0) -> Optional[int]:
        """
        Pop an event ID from the processing queue.
        
        Args:
            timeout: Blocking timeout in seconds (0 = blocking indefinitely).
            
        Returns:
            Event ID if available, None if timeout.
        """
        result = self.redis.blpop(self.queue_name, timeout=timeout)
        
        if result is None:
            return None
            
        _, event_id_str = result
        event_id = int(event_id_str)
        
        # Track as currently processing
        self.redis.sadd(self.processing_key, str(event_id))
        
        logger.debug(f"Popped event {event_id} from queue")
        return event_id

    def mark_event_processed(self, event_id: int) -> None:
        """
        Mark an event as successfully processed.
        
        Args:
            event_id: The database ID of the processed event.
        """
        # Remove from processing set
        self.redis.srem(self.processing_key, str(event_id))
        
        # Add to processed set (with TTL to prevent unbounded growth)
        self.redis.sadd(self.processed_key, str(event_id))
        self.redis.expire(self.processed_key, 86400 * 7)  # 7 days TTL
        
        logger.debug(f"Marked event {event_id} as processed")

    def retry_event(self, event_id: int, retry_count: int) -> bool:
        """
        Push an event to the retry queue.
        
        Args:
            event_id: The database ID of the event to retry.
            retry_count: Current retry count.
            
        Returns:
            True if queued for retry, False if moved to dead letter queue.
        """
        settings = get_settings()
        
        # Remove from processing set
        self.redis.srem(self.processing_key, str(event_id))
        
        if retry_count >= settings.MAX_RETRIES:
            # Move to dead letter queue
            self.redis.rpush(self.dead_letter_queue_name, str(event_id))
            logger.warning(f"Event {event_id} moved to dead letter queue after {retry_count} retries")
            return False
        
        # Push to retry queue with delay (using Redis sorted set for delayed processing)
        # Score is the timestamp when the event should be processed
        import time
        delay_score = time.time() + settings.RETRY_DELAY_SECONDS
        self.redis.zadd(f"{self.retry_queue_name}:scheduled", {str(event_id): delay_score})
        
        logger.info(f"Event {event_id} scheduled for retry {retry_count + 1}/{settings.MAX_RETRIES}")
        return True

    def process_scheduled_retries(self) -> int:
        """
        Move due retry events from scheduled set to main queue.
        
        Returns:
            Number of events moved to main queue.
        """
        import time
        current_time = time.time()
        
        # Get events that are due for retry
        due_events = self.redis.zrangebyscore(
            f"{self.retry_queue_name}:scheduled",
            "-inf",
            current_time,
        )
        
        if due_events:
            # Remove from scheduled set
            self.redis.zrem(f"{self.retry_queue_name}:scheduled", *due_events)
            
            # Add to main queue
            if due_events:
                self.redis.rpush(self.queue_name, *due_events)
            
            logger.info(f"Moved {len(due_events)} events from retry queue to main queue")
            return len(due_events)
        
        return 0

    def is_event_processed(self, event_id: int) -> bool:
        """Check if an event has already been processed."""
        return self.redis.sismember(self.processed_key, str(event_id))

    def is_event_in_queue(self, event_id: int) -> bool:
        """Check if an event is currently in any queue."""
        # Check processing set
        if self.redis.sismember(self.processing_key, str(event_id)):
            return True
        
        # Check main queue (expensive operation, use sparingly)
        # For production, consider maintaining a separate index
        return False

    def get_queue_stats(self) -> dict:
        """
        Get queue statistics for monitoring.
        
        Returns:
            Dictionary with queue statistics.
        """
        return {
            "main_queue_length": self.redis.llen(self.queue_name),
            "retry_queue_length": self.redis.zcard(f"{self.retry_queue_name}:scheduled"),
            "dead_letter_queue_length": self.redis.llen(self.dead_letter_queue_name),
            "currently_processing": self.redis.scard(self.processing_key),
        }

    def clear_queue(self) -> None:
        """Clear all queues (useful for testing)."""
        self.redis.delete(self.queue_name)
        self.redis.delete(f"{self.retry_queue_name}:scheduled")
        self.redis.delete(self.dead_letter_queue_name)
        self.redis.delete(self.processing_key)
        self.redis.delete(self.processed_key)
        logger.warning("All queues cleared")
