import logging
import inngest

# Create an Inngest client
inngest_client = inngest.Inngest(
    app_id="linkedin",   # use your project name here
    logger=logging.getLogger("gunicorn"),
)
