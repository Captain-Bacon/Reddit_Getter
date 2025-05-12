import re
import logging
from typing import Optional # For type hints
from error_handler import URLValidationError

logger = logging.getLogger(__name__)

def validate_reddit_url(url: str) -> bool:
    """Validate if the given URL string matches known Reddit post URL patterns.

    Handles standard (www.reddit.com), old (old.reddit.com), and short (redd.it)
    formats, including potential query parameters or fragments.

    Args:
        url: The URL string to validate.

    Returns:
        True if the URL matches a known Reddit post pattern, False otherwise.
    """
    if not isinstance(url, str):
        logger.warning(f"URL validation failed: Input is not a string, but {type(url)}.")
        return False # Or raise TypeError, but for validation, returning False is often preferred.

    logger.debug(f"Validating URL: {url}")
    # Adjusted regex patterns to be more robust and handle optional trailing slashes,
    # query parameters, and fragments.
    reddit_url_pattern = r'^https?://(?:www\.)?reddit\.com/r/[\w\d_]+/comments/[\w\d_]+(?:/[^\s/?#]*)*/?(?:\?[^\s#]*)?(?:#[^\s]*)?$'
    old_reddit_pattern = r'^https?://old\.reddit\.com/r/[\w\d_]+/comments/[\w\d_]+(?:/[^\s/?#]*)*/?(?:\?[^\s#]*)?(?:#[^\s]*)?$'
    short_reddit_pattern = r'^https?://(?:www\.)?redd\.it/[\w\d_]+/?(?:\?[^\s#]*)?(?:#[^\s]*)?$'
    
    try:
        is_valid = bool(
            re.match(reddit_url_pattern, url) or 
            re.match(old_reddit_pattern, url) or 
            re.match(short_reddit_pattern, url)
        )
        if is_valid:
            logger.debug(f"URL validation successful for: {url}")
        else:
            logger.debug(f"URL validation failed for: {url}")
        return is_valid
    except Exception as e:
        logger.error(f"Regex error during URL validation for '{url}': {e}", exc_info=True)
        # This is unexpected, as regex compilation errors should be caught at import time if patterns are static.
        # Runtime errors in re.match are rare with valid patterns.
        # We could raise a custom internal error here or re-raise e.
        # For now, treat as validation failure but log as severe.
        return False 

def extract_post_id(url: str) -> Optional[str]:
    """Extracts the Reddit post ID from a URL string.

    First validates the URL using `validate_reddit_url`. If valid, attempts
    to extract the ID using regex patterns for standard and short URLs.

    Args:
        url: The URL string to process.

    Returns:
        The extracted post ID string if found, otherwise None.
    """
    logger.debug(f"Attempting to extract post ID from URL: {url}")
    if not validate_reddit_url(url): # Relies on validate_reddit_url to log its own failure reason
        logger.warning(f"Post ID extraction skipped: URL validation failed for {url}")
        # No specific URLValidationError raised here as validate_reddit_url should handle it or return False
        return None

    try:
        # Pattern for standard and old Reddit URLs (captures the ID)
        # e.g., /r/subreddit/comments/POST_ID/optional_title/
        standard_match = re.search(r'/comments/([\w\d_]+)(?:/|$)', url)
        if standard_match:
            post_id = standard_match.group(1)
            logger.info(f"Extracted post ID '{post_id}' from standard URL: {url}")
            return post_id

        # Pattern for short URLs (redd.it/POST_ID)
        short_match = re.search(r'redd\.it/([\w\d_]+)(?:/|$|\?)', url)
        if short_match:
            post_id = short_match.group(1)
            logger.info(f"Extracted post ID '{post_id}' from short URL: {url}")
            return post_id
        
        logger.warning(f"Could not extract post ID from validated URL: {url}. Pattern mismatch.")
        # This case implies the URL passed initial validation but ID extraction regex failed.
        # Could raise URLValidationError here if strictness is desired.
        # For now, returning None and logging is consistent with previous behavior.
        return None
    except Exception as e:
        logger.error(f"Regex error during post ID extraction for '{url}': {e}", exc_info=True)
        # Treat unexpected regex errors as extraction failure
        return None


# --- Test Block ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    test_urls = {
        "valid_standard": "https://www.reddit.com/r/learnpython/comments/123abc/my_python_post/",
        "valid_standard_no_title": "http://reddit.com/r/pics/comments/xyz789/",
        "valid_old": "https://old.reddit.com/r/gaming/comments/qwerty/another_post_title_here",
        "valid_short": "https://redd.it/123xyz",
        "valid_short_www": "http://www.redd.it/abc987",
        "valid_with_query": "https://www.reddit.com/r/askreddit/comments/zyxwuv/some_question/?utm_source=share&utm_medium=web2x&context=3",
        "user_provided_test": "https://www.reddit.com/r/ADHD/comments/1kg08k0/whats_a_weird_little_adhd_trick_that_actually/",
        "invalid_not_reddit": "https://www.google.com",
        "invalid_malformed_reddit": "https://www.reddit.com/r/onlysubreddit/",
        "invalid_short_incomplete": "https://redd.it/",
        "valid_trailing_slash_and_query": "https://www.reddit.com/r/learnpython/comments/123abc/?ref=test",
        "valid_no_trailing_title_or_slash" : "https://www.reddit.com/r/subreddit/comments/postid",
        "valid_short_with_query": "https://redd.it/123xyz?source=test"
    }

    for name, url_to_test in test_urls.items():
        logger.info(f"--- Testing URL: '{name}' ({url_to_test}) ---")
        is_valid = validate_reddit_url(url_to_test)
        logger.info(f"Validation result for '{url_to_test}': {is_valid}")
        
        if is_valid:
            post_id = extract_post_id(url_to_test)
            logger.info(f"Extracted Post ID for '{url_to_test}': {post_id if post_id else 'None'}")
            # Basic checks for some known IDs
            if name == "valid_standard" and post_id != "123abc":
                logger.error(f"ID Mismatch for {name}! Expected 123abc, got {post_id}")
            if name == "valid_short" and post_id != "123xyz":
                 logger.error(f"ID Mismatch for {name}! Expected 123xyz, got {post_id}")
            if name == "user_provided_test" and post_id != "1kg08k0":
                logger.error(f"ID Mismatch for {name}! Expected 1kg08k0, got {post_id}")
        else:
            # If not valid, extract_post_id should also return None
            post_id_attempt = extract_post_id(url_to_test)
            if post_id_attempt is not None:
                logger.error(f"Error: Extracted Post ID '{post_id_attempt}' from an INvalid URL: {url_to_test}")
        logger.info("---")
    
    logger.info("URL Processor tests complete.") 