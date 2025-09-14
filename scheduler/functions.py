import logging
import asyncio
from django.utils import timezone
from asgiref.sync import sync_to_async
from scheduler.client import inngest_client
import inngest
from posts.models import Post

logger = logging.getLogger(__name__)


def get_now():
    """
    Return current timestamp (float) in seconds.
    """
    return timezone.now().timestamp()


def workflow_share_on_linkedin_node(instance):
    """
    Helper function to verify and share a post on LinkedIn.
    Runs synchronously.
    """
    try:
        instance.verify_can_share_on_linkedin()
    except Exception:
        logger.error(f"Post {instance.id} cannot be shared on LinkedIn")
        return False, "Did not share on LinkedIn"

    try:
        instance.perform_share_on_linkedin(mock=False, save=True)
        logger.info(f"Post {instance.id} successfully shared on LinkedIn")
        return True, "Shared on LinkedIn"
    except Exception as e:
        logger.error(f"Error sharing Post {instance.id} on LinkedIn: {e}")
        return False, f"Error: {e}"


# Create an Inngest function
@inngest_client.create_function(
    fn_id="post_scheduler",
    trigger=inngest.TriggerEvent(event="posts/post.scheduled"),
)
async def post_scheduler(ctx: inngest.Context) -> str:
    """
    This Inngest function is triggered when a post is scheduled.
    It will fetch the post and share it on LinkedIn if needed.
    """
    event_data = ctx.event.data
    post_id = event_data.get("object_id")

    if not post_id:
        logger.error("No post ID found in event data")
        return "no post_id"

    # Get post instance safely
    try:
        post = await sync_to_async(Post.objects.get)(id=post_id)
    except Post.DoesNotExist:
        logger.error(f"Post with id {post_id} does not exist")
        return "post not found"

    # Mark start time
    start_at = await sync_to_async(get_now)()
    post.share_start_at = timezone.now()
    await sync_to_async(post.save)(update_fields=["share_start_at"])

    # Check if LinkedIn share is required
    if post.share_on_linkedin and not post.shared_at_linkedin:
        logger.info(f"Sharing Post {post.id} on LinkedIn...")
        success, msg = await sync_to_async(workflow_share_on_linkedin_node)(post)

        if success:
            post.share_complete_at = timezone.now()
            await sync_to_async(post.save)(update_fields=["share_complete_at"])
        else:
            return f"failed: {msg}"
    else:
        logger.info(f"Post {post.id} does not require LinkedIn sharing")

    return "done"
