from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from helper import linkedin
from asgiref.sync import async_to_sync
import inngest
from scheduler.client import inngest_client
from datetime import timedelta

User = settings.AUTH_USER_MODEL  # "auth.User"


class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    share_now = models.BooleanField(default=None, null=True, blank=True)
    share_at = models.DateTimeField(null=True, blank=True)
    share_start_at = models.DateTimeField(null=True, blank=True)
    share_complete_at = models.DateTimeField(null=True, blank=True)
    share_on_linkedin = models.BooleanField(default=False)
    shared_at_linkedin = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self, *args, **kwargs):
        """
        Validate post settings before saving.
        """
        super().clean(*args, **kwargs)
        if self.share_now is None and self.shared_at_linkedin is None:
            raise ValidationError({
                "share_at": "You must select a time to share or share it now."
            })

        # If it's marked for LinkedIn, run verification
        if self.share_on_linkedin:
            self.verify_can_share_on_linkedin()

    def get_scheduled_platform(self):
        """
        Returns a list of platforms this post is scheduled for.
        """
        platforms = []
        if self.share_on_linkedin:
            platforms.append("LinkedIn")
        return platforms

    def save(self, *args, **kwargs):
        """
        Save the Post instance and optionally schedule sharing via Inngest.
        """
        do_schedule_post = False

        if all([
            self.share_now is not None or self.share_at is not None,
            self.share_complete_at is None and self.share_start_at is None
        ]):
            do_schedule_post = True
            if self.share_now:
                self.share_at = timezone.now()

        super().save(*args, **kwargs)

        if do_schedule_post:
            time_delay = (timezone.now() + timedelta(seconds=10)).timestamp() * 1000
            if self.share_at:
                time_delay = (self.share_at + timedelta(seconds=45)).timestamp() * 1000

            inngest_client.send_sync(
                inngest.Event(
                    name="posts/post.scheduled",
                    id=f"posts/post.scheduled.{self.id}",
                    data={"object_id": self.id},
                    ts=int(time_delay)
                )
            )

    def perform_share_on_linkedin(self, mock=False, save=False):
        """
        Share this post to LinkedIn if it hasn't been shared already.
        """
        if self.shared_at_linkedin:
            return self

        # Validate first
        self.verify_can_share_on_linkedin()

        if not mock:
            try:
                async_to_sync(linkedin.post_to_linkedin)(self.user, self.content)
            except Exception:
                raise ValidationError({
                    "content": "Could not share to LinkedIn."
                })

        self.shared_at_linkedin = timezone.now()
        self.share_on_linkedin = False

        if save:
            self.save(update_fields=["shared_at_linkedin", "share_on_linkedin"])

        return self

    def verify_can_share_on_linkedin(self):
        """
        Validate if this post can be shared on LinkedIn.
        """
        if len(self.content) < 5:
            raise ValidationError({
                "content": "Content must be at least 5 characters long."
            })
        if self.shared_at_linkedin:
            raise ValidationError({
                "share_on_linkedin": f"Content already shared on LinkedIn at {self.shared_at_linkedin}."
            })
        try:
            async_to_sync(linkedin.get_linkedin_user_details)(self.user)
        except linkedin.UserNotConnectedLinkedIn:
            raise ValidationError({
                "user": "This user is not able to share on LinkedIn."
            })
