from dotenv import load_dotenv
import os
import praw
import logging
from error_handler import APIAuthenticationError, ConfigError

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Define the redirect URI used in your Reddit app settings
REDIRECT_URI = "http://localhost:8080"
# Define the scopes your application needs
# "identity" - to know who authorized
# "read" - to read posts and comments
# Add other scopes if needed in the future, e.g., "history" for user's post history
REQUIRED_SCOPES = ["identity", "read"]

def initialize_reddit_client() -> praw.Reddit:
    """Initializes and returns a PRAW Reddit instance.

    Handles OAuth2 Code Flow for installed applications:
    1. Tries to use a REDDIT_REFRESH_TOKEN from environment variables for non-interactive sessions.
    2. If no refresh token is found, guides the user through the one-time
       authorization process to obtain one.

    Raises:
        ConfigError: If required environment variables (ID, User-Agent) are missing.
        APIAuthenticationError: If authentication or token refresh fails.
        Exception: For other PRAW or unexpected errors during initialization.
    """
    logger.info("Attempting to initialize Reddit client using Code Flow...")

    client_id = os.getenv("REDDIT_CLIENT_ID")
    user_agent = os.getenv("REDDIT_USER_AGENT")
    refresh_token = os.getenv("REDDIT_REFRESH_TOKEN")

    if not client_id:
        raise ConfigError("REDDIT_CLIENT_ID is not set in environment variables (.env).")
    if not user_agent:
        raise ConfigError("REDDIT_USER_AGENT is not set in environment variables (.env).")

    try:
        if refresh_token:
            logger.info("Found REDDIT_REFRESH_TOKEN. Attempting to authenticate.")
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=None,  # Installed apps typically don't use a secret with Code Flow / refresh token
                refresh_token=refresh_token,
                user_agent=user_agent,
            )
            # Verify authentication by trying to access a protected attribute
            # and checking scopes
            authenticated_user = reddit.user.me()
            current_scopes = reddit.auth.scopes()
            logger.info(f"Successfully authenticated as u/{authenticated_user} using refresh token.")
            logger.debug(f"Current authorized scopes: {current_scopes}")
            
            # Optional: Check if all required scopes are present
            if not all(scope in current_scopes for scope in REQUIRED_SCOPES):
                logger.warning(f"Refresh token might not have all required scopes. Expected: {REQUIRED_SCOPES}, Got: {current_scopes}")
                logger.warning("If issues arise, you may need to re-authorize to get a new refresh token with correct scopes.")

        else:
            logger.info("REDDIT_REFRESH_TOKEN not found. Starting one-time authorization.")
            # No refresh token, so we need to authorize.
            # client_secret is None for installed apps during the auth URL generation and code exchange.
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=None,
                redirect_uri=REDIRECT_URI,
                user_agent=user_agent,
            )

            # Generate the authorization URL
            # state is recommended for security but can be a simple unique string for local scripts
            auth_url = reddit.auth.url(scopes=REQUIRED_SCOPES, state="SOME_RANDOM_STATE_STRING", duration="permanent")
            
            print("\n--- Reddit API Authorization Required ---")
            print("1. Open the following URL in your browser:")
            print(f"   {auth_url}")
            print("2. Log in to Reddit (you can use your Google account) and authorize the application.")
            print(f"3. You will be redirected to a URL starting with '{REDIRECT_URI}'.")
            print("   Copy the value of the 'code' parameter from that URL.")
            print("   (e.g., if redirected to http://localhost:8080/?state=...&code=ABCDEFG, copy 'ABCDEFG')")
            
            auth_code = input("Enter the 'code' from the redirect URL: ").strip()

            if not auth_code:
                raise APIAuthenticationError("Authorization code was not provided.")

            logger.info("Received authorization code. Attempting to obtain refresh token...")
            new_refresh_token = reddit.auth.authorize(auth_code)
            logger.info("Successfully obtained new refresh token.")
            
            print("\n--- Authorization Successful! ---")
            print(f"Obtained new REDDIT_REFRESH_TOKEN: {new_refresh_token}")
            print("IMPORTANT: Please add the following line to your .env file for future use:")
            print(f"REDDIT_REFRESH_TOKEN={new_refresh_token}")
            print("Then re-run the script.")
            print("-----------------------------------")
            
            # At this point, 'reddit' is authorized for the current session.
            # The user needs to manually save the refresh token for subsequent runs.
            authenticated_user = reddit.user.me()
            logger.info(f"Initial authorization successful for u/{authenticated_user}.")

        # A simple check to ensure the client is somewhat functional after setup
        # This might still fail if there are issues beyond basic auth (e.g. reddit is down)
        # but confirms PRAW thinks it's ready.
        logger.debug(f"PRAW read_only status: {reddit.read_only}")
        logger.info("Reddit client initialized successfully.")
        return reddit

    except praw.exceptions.PRAWException as e:
        logger.error(f"A PRAW-specific error occurred during Reddit client setup: {e}", exc_info=True)
        # More specific PRAW error handling can be added here if needed
        if "invalid_grant" in str(e).lower():
            msg = "OAuth 'invalid_grant' error. This can happen if the authorization code is invalid/expired, or the refresh token is revoked/invalid. If this was the first run, ensure you copied the 'code' correctly. If using a refresh token, it may need to be regenerated by removing it from .env and re-authorizing."
            raise APIAuthenticationError(msg) from e
        elif "invalid_request" in str(e).lower() and "redirect_uri" in str(e).lower():
            msg = f"OAuth 'invalid_request' error, possibly related to redirect_uri. Ensure '{REDIRECT_URI}' is correctly set in your Reddit app settings and matches the one in the script."
            raise APIAuthenticationError(msg) from e
        raise APIAuthenticationError(f"PRAW error during client setup: {e}") from e
    except Exception as e:
        logger.error(f"An unexpected error occurred during Reddit client setup: {e}", exc_info=True)
        raise APIAuthenticationError(f"An unexpected error occurred during Reddit client setup: {e}") from e

def test_authentication():
    """Tests the Reddit client initialization and basic functionality."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s [%(name)s] - %(message)s')
    logger.info("--- Testing Reddit Client Initialization (Code Flow) ---")
    try:
        reddit = initialize_reddit_client()
        if reddit and not reddit.read_only: # Code flow should result in an authenticated user
            user = reddit.user.me()
            scopes = reddit.auth.scopes()
            logger.info(f"Successfully authenticated as Reddit user: u/{user.name}")
            logger.info(f"Authorized scopes: {scopes}")
            # Example: Fetch top 3 posts from r/popular to test read access
            # logger.info("Fetching top 3 posts from r/popular...")
            # for i, submission in enumerate(reddit.subreddit("popular").hot(limit=3)):
            #     logger.info(f"  {i+1}. {submission.title[:50]}...")
            # logger.info("Successfully fetched posts from r/popular.")
        elif reddit and reddit.read_only:
            logger.warning("Client initialized in read-only mode. Refresh token might be missing or authorization failed silently for authenticated access.")
        else:
            logger.error("Reddit client initialization failed or did not return an instance.")

    except ConfigError as e:
        logger.error(f"Configuration Error during test: {e}")
    except APIAuthenticationError as e:
        logger.error(f"API Authentication Error during test: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during authentication test: {e}", exc_info=True)
    finally:
        logger.info("--- Test Finished ---")

if __name__ == "__main__":
    # To test:
    # 1. Ensure REDDIT_CLIENT_ID and REDDIT_USER_AGENT are in your .env file.
    # 2. Remove REDDIT_REFRESH_TOKEN from .env (if it exists) for the first run.
    # 3. Run `python auth.py`. Follow the printed instructions to authorize and get a refresh token.
    # 4. Add the printed REDDIT_REFRESH_TOKEN to your .env file.
    # 5. Run `python auth.py` again. It should now authenticate non-interactively.
    test_authentication() 