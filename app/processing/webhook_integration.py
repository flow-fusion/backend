"""Webhook integration service for pushing events to the processing queue.

This is the INTEGRATION POINT between the Webhook Layer and Processing Layer.
"""

from typing import Optional
from app.shared.logging_config import get_logger
from app.processing.event_queue_service import EventQueueService

logger = get_logger("webhook_integration")


class WebhookIntegrationService:
    """
    Service for integrating the webhook layer with the processing layer.
    
    This service is called by the webhook receiver after saving an event
    to push the event ID to the processing queue.
    
    Usage:
        # In webhook handler after saving event
        integration = WebhookIntegrationService()
        integration.queue_event_for_processing(event_id)
    """

    def __init__(self, queue_service: Optional[EventQueueService] = None):
        self.queue_service = queue_service or EventQueueService()

    def queue_event_for_processing(self, event_id: int) -> bool:
        """
        Queue an event for async processing.
        
        Call this method after saving an event to the database.
        
        Args:
            event_id: The database ID of the event to process.
            
        Returns:
            True if event was queued, False if skipped (duplicate).
        """
        logger.info(f"Queueing event {event_id} for processing")
        
        success = self.queue_service.push_event(event_id)
        
        if success:
            logger.info(f"Event {event_id} queued for processing")
        else:
            logger.debug(f"Event {event_id} skipped (already queued/processed)")
        
        return success

    def get_queue_status(self) -> dict:
        """
        Get current queue status.
        
        Returns:
            Dictionary with queue statistics.
        """
        return self.queue_service.get_queue_stats()


# Convenience function for webhook handlers
def queue_event(event_id: int) -> bool:
    """
    Queue an event for processing.
    
    Convenience function for use in webhook handlers.
    
    Args:
        event_id: The database ID of the event.
        
    Returns:
        True if event was queued.
    """
    service = WebhookIntegrationService()
    return service.queue_event_for_processing(event_id)
