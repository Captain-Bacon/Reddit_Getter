import sys # Required for checking if praw is in loaded modules
from typing import Type, Union # Added for type hinting

class RedditExtractorError(Exception):
    """Base exception class for Reddit Extractor errors."""
    pass

class URLValidationError(RedditExtractorError):
    """Raised when a URL is invalid or not a Reddit post URL."""
    pass

class APIAuthenticationError(RedditExtractorError):
    """Raised when there's an issue with Reddit API authentication."""
    pass

class PostRetrievalError(RedditExtractorError):
    """Raised when a post cannot be retrieved."""
    pass

class CommentRetrievalError(RedditExtractorError):
    """Raised when comments cannot be retrieved."""
    pass

class OutputError(RedditExtractorError):
    """Raised when there's an issue with generating or saving output."""
    pass

class ConfigError(RedditExtractorError):
    """Raised for configuration-related issues (e.g., missing .env values)."""
    pass


def is_retryable_error(error: Exception) -> bool:
    """Determine if an error is potentially retryable based on its string representation or type.

    Checks for common HTTP error codes (5xx), rate limit messages, timeouts, 
    and connection issues within the error string or specific PRAW/prawcore exception types.

    Args:
        error: The exception instance to check.

    Returns:
        True if the error seems retryable, False otherwise.
    """
    try:
        # PRAW 7.x moved many exceptions to prawcore
        import prawcore.exceptions
        import praw.exceptions # For APITratelimitException or others that might remain

        # Check for specific PRAW/prawcore exception types first
        if isinstance(error, (
            prawcore.exceptions.RequestException, 
            prawcore.exceptions.ResponseException,
            prawcore.exceptions.PrawcoreException, # General prawcore base
            praw.exceptions.RedditAPIException # Add RedditAPIException here for explicit check
        )):
            # For PRAW/prawcore exceptions, check status codes if available
            if hasattr(error, 'response') and error.response is not None:
                if error.response.status_code == 429: # HTTP 429: Too Many Requests (Rate Limit)
                    return True
                if error.response.status_code in [500, 502, 503, 504]: # Server-side errors
                    return True
            # Fall through to string matching for other prawcore/praw exceptions if no specific status code match
            pass 
    except ImportError:
        # If praw/prawcore can't be imported, fall back to string matching only
        pass 

    error_str = str(error).lower()
    retryable_phrases = [
        'rate limit', 'ratelimit',
        'timeout', 'time-out', 'timed out',
        'connection failed', 'connection reset', 'connection refused', 'connection error',
        'temporary', 'transient',
        '500', '502', '503', '504', 
        'server error', 'internal server error',
        'service unavailable',
        'please try again later'
    ]
    return any(phrase in error_str for phrase in retryable_phrases)


def format_user_error_message(error: Exception) -> str:
    """Formats an exception into a user-friendly error message string.

    Handles custom RedditExtractorError types and falls back to a generic 
    message for other exception types.

    Args:
        error: The exception instance to format.

    Returns:
        A user-friendly string describing the error.
    """
    if isinstance(error, URLValidationError):
        return f"URL Validation Error: {str(error)}"
    elif isinstance(error, APIAuthenticationError):
        return f"API Authentication Error: {str(error)}. Please check your API credentials in the .env file."
    elif isinstance(error, ConfigError):
        return f"Configuration Error: {str(error)}."
    elif isinstance(error, PostRetrievalError):
        return f"Post Retrieval Error: {str(error)}. The post might be private, deleted, or the ID is incorrect."
    elif isinstance(error, CommentRetrievalError):
        return f"Comment Retrieval Error: {str(error)}."
    elif isinstance(error, OutputError):
        return f"Output Error: {str(error)}."
    else:
        # Check for PRAW exceptions only if PRAW seems loaded
        # This avoids NameError if the initial error happened before praw was imported
        is_praw_exception = False
        if 'praw' in sys.modules:
            try:
                # Dynamically import PRAWException only if needed
                from praw.exceptions import PRAWException
                if isinstance(error, PRAWException):
                    is_praw_exception = True
            except ImportError:
                 # Should not happen if 'praw' in sys.modules, but handles edge cases
                 pass 
                 
        if is_praw_exception:
            return f"Reddit API Error: {str(error)}"
        elif isinstance(error, RedditExtractorError): 
            return f"Application Error: {str(error)}"
        else:
            # Fallback for truly unexpected errors
            return f"An unexpected error occurred: {str(error)}" 