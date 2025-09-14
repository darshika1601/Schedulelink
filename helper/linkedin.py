import httpx
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model

class UserNotConnectedLinkedIn(Exception):
    pass

# Async-compatible ORM wrapper
async def get_linkedin_user_details(user):
    try:
        linkedin_social = await sync_to_async(user.socialaccount_set.get)(provider="linkedin")
    except:
        raise UserNotConnectedLinkedIn("LinkedIn is not connected on this user.")
    return linkedin_social

async def get_share_headers(linkedin_social):
    tokens = await sync_to_async(list)(linkedin_social.socialtoken_set.all())
    if not tokens:
        raise Exception("LinkedIn connection is invalid. Please login again.")
    social_token = tokens[0]
    return {
        "Authorization": f"Bearer {social_token.token}",
        "X-Restli-Protocol-Version": "2.0.0"
    }

# Fully async post function using httpx
async def post_to_linkedin(user, text: str):
    User = get_user_model()
    if not isinstance(user, User):
        raise Exception("Must be a user")

    linkedin_social = await get_linkedin_user_details(user)
    linkedin_user_id = linkedin_social.uid
    if not linkedin_user_id:
        raise Exception("Invalid LinkedIn User Id")

    headers = await get_share_headers(linkedin_social)
    endpoint = "https://api.linkedin.com/v2/ugcPosts"
    payload = {
        "author": f"urn:li:person:{linkedin_user_id}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()

    return response
