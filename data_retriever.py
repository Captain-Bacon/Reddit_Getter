import time
import praw # For praw.exceptions
import random # For jitter in backoff
import logging # For logging retries and errors
from typing import Callable, Any, Dict, List, Optional # For type hinting

# Import custom errors and retry logic helper
from error_handler import (
    PostRetrievalError, CommentRetrievalError, APIAuthenticationError,
    is_retryable_error
)
# from auth import initialize_reddit_client # Already imported in __main__ if needed for testing
# from url_processor import extract_post_id, validate_reddit_url # For testing in __main__

logger = logging.getLogger(__name__)

# --- Retry Decorator ---
def retry_with_backoff(max_retries: int = 3, base_delay: float = 2, max_delay: float = 30) -> Callable:
    """Decorator factory for retrying a function with exponential backoff and jitter.

    Args:
        max_retries: Maximum number of retries before giving up.
        base_delay: Initial delay in seconds for the first retry.
        max_delay: Maximum delay in seconds between retries.

    Returns:
        A decorator function.
    """
    def decorator(func: Callable) -> Callable:
        """The actual decorator that wraps the function."""
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """The wrapper function executing the retry logic."""
            retries = 0
            current_delay = base_delay
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if retries >= max_retries or not is_retryable_error(e):
                        logger.error(f"Non-retryable error or max retries reached for {func.__name__}: {e}")
                        # Re-raise the original error or a more specific custom one if identifiable
                        if isinstance(e, praw.exceptions.PRAWException):
                             # Could be APIAuthenticationError if it's a 401/403, or generic Post/CommentRetrievalError
                            if "401" in str(e) or "403" in str(e): # Basic check
                                raise APIAuthenticationError(f"Authentication failed during {func.__name__}: {e}") from e
                            elif func.__name__ == "fetch_post_data":
                                raise PostRetrievalError(f"API error in {func.__name__}: {e}") from e
                            elif func.__name__ == "fetch_comments_data":
                                raise CommentRetrievalError(f"API error in {func.__name__}: {e}") from e
                        raise # Re-raise original if not caught more specifically
                    
                    jitter = random.uniform(0, current_delay * 0.1) # Add up to 10% jitter
                    actual_delay = min(current_delay + jitter, max_delay)
                    
                    logger.warning(
                        f"Error in {func.__name__}: {e}. "
                        f"Retrying in {actual_delay:.2f} seconds... (Attempt {retries + 1}/{max_retries})"
                    )
                    time.sleep(actual_delay)
                    retries += 1
                    current_delay = min(current_delay * 2, max_delay) # Exponential backoff
        return wrapper
    return decorator

# --- Data Fetching Functions ---
@retry_with_backoff()
def fetch_post_data(reddit_client: praw.Reddit, post_id: str, include_raw_media_details: bool = False) -> Dict[str, Any]:
    """Fetches and structures data for a given Reddit post ID, applying retry logic.

    Args:
        reddit_client: An initialized PRAW Reddit client instance.
        post_id: The ID of the Reddit post to fetch.
        include_raw_media_details: Whether to include verbose raw media fields from PRAW.

    Returns:
        A dictionary containing structured data about the post.

    Raises:
        PostRetrievalError: If the post cannot be retrieved (e.g., not found, private).
        APIAuthenticationError: If authentication fails during retrieval.
        (Potentially others inherited from the retry decorator for PRAW exceptions)
    """
    logger.info(f"Fetching post data for ID: {post_id}")
    try:
        submission = reddit_client.submission(id=post_id)
        # submission.load() # Ensure all attributes are loaded - .load() is deprecated in PRAW 7+

        # Check if post exists or is accessible
        if not hasattr(submission, 'title') or submission.title is None:
             # This might happen for deleted/removed posts if load() doesn't error
            logger.warning(f"Post with ID {post_id} appears to be deleted or inaccessible.")
            raise PostRetrievalError(f"Post with ID {post_id} is deleted, private, or does not exist.")

        structured_media_list = extract_media_info(submission)

        post_data = {
            'id': submission.id,
            'title': submission.title,
            'author': submission.author.name if submission.author else '[deleted]',
            'created_utc': submission.created_utc,
            'url': submission.url,
            'permalink': f"https://www.reddit.com{submission.permalink}",
            'domain': submission.domain,
            'selftext': submission.selftext,
            'score': submission.score,
            'upvote_ratio': submission.upvote_ratio,
            'num_comments': submission.num_comments,
            'is_original_content': submission.is_original_content,
            'is_self': submission.is_self,
            'is_video': submission.is_video,
            'stickied': submission.stickied,
            'over_18': submission.over_18,
            'spoiler': submission.spoiler,
            'locked': submission.locked,
            'subreddit': submission.subreddit.display_name,
            'subreddit_id': submission.subreddit_id,
            'gilded': submission.gilded,
            'media_info': structured_media_list,
        }

        if include_raw_media_details:
            post_data['_raw_media'] = submission.media
            post_data['_raw_media_embed'] = submission.media_embed
            post_data['_raw_secure_media'] = submission.secure_media
            post_data['_raw_secure_media_embed'] = submission.secure_media_embed
            if hasattr(submission, 'gallery_data'):
                post_data['_raw_gallery_data'] = submission.gallery_data
            if hasattr(submission, 'media_metadata') and submission.media_metadata:
                post_data['_raw_media_metadata'] = submission.media_metadata
        
        logger.info(f"Successfully fetched post data for ID: {post_id}")
        return post_data
    except praw.exceptions.PRAWException as e:
        logger.error(f"PRAWException fetching post {post_id}: {e}")
        if "404" in str(e) or "not found" in str(e).lower():
            raise PostRetrievalError(f"Post with ID {post_id} not found (404).") from e
        elif "401" in str(e) or "403" in str(e):
            raise APIAuthenticationError(f"Authentication error fetching post {post_id}.") from e
        raise PostRetrievalError(f"Failed to fetch post {post_id} due to API error: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching post {post_id}: {e}", exc_info=True)
        raise PostRetrievalError(f"An unexpected error occurred while fetching post {post_id}: {e}") from e


def _process_comment(comment: praw.models.Comment, depth: int = 0, max_depth: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Recursively processes a PRAW Comment object into a structured dictionary.

    Handles comment attributes and recursively processes replies up to max_depth.
    Skips MoreComments objects and comments without authors/bodies (likely deleted).

    Args:
        comment: The PRAW Comment object to process.
        depth: The current depth of this comment in the reply tree.
        max_depth: The maximum depth of replies to process. None means infinite.

    Returns:
        A dictionary representing the comment and its replies, or None if the
        comment should be skipped.
    """
    if not hasattr(comment, 'body') or comment.author is None:
        logger.debug(f"Skipping comment {comment.id}: Missing body or author.")
        return None
    if isinstance(comment, praw.models.MoreComments):
         logger.debug(f"Skipping MoreComments object with ID: {comment.id}")
         return None # Explicitly skip MoreComments if encountered despite replace_more

    # Prepare the basic comment data
    comment_data_to_return = {
        'id': comment.id,
        'author': comment.author.name if comment.author else '[deleted]',
        'body': comment.body,
        'created_utc': comment.created_utc,
        'score': comment.score,
        'is_submitter': comment.is_submitter,
        'stickied': comment.stickied,
        'parent_id': comment.parent_id,
        'permalink': f"https://www.reddit.com{comment.permalink}",
        'depth': depth,
        'replies': [] # Initialize with empty replies
    }

    # Check if we should process replies for this comment
    # If max_depth is reached, return the comment data as is (with empty replies)
    if max_depth is not None and depth >= max_depth:
        logger.debug(f"Reached max depth ({depth}) for comment {comment.id}. Not processing its replies.")
        return comment_data_to_return
    
    # If depth allows, process replies and update the 'replies' field
    if hasattr(comment, 'replies'):
        try:
            # limit=None should theoretically fetch all direct replies for this comment branch
            comment.replies.replace_more(limit=None) 
            for reply_praw_object in comment.replies: # Renamed 'reply' to avoid name collision if any module named 'reply' exists
                processed_reply_data = _process_comment(reply_praw_object, depth + 1, max_depth)
                if processed_reply_data:
                    comment_data_to_return['replies'].append(processed_reply_data)
        except Exception as e:
            logger.warning(f"Error processing replies for comment {comment.id}: {e}. Skipping further replies for this comment.", exc_info=True)
            # Replies will remain as processed so far, or empty if error was immediate.
                
    return comment_data_to_return

@retry_with_backoff()
def fetch_comments_data(submission: praw.models.Submission, sort_order: str = 'best', num_comments: int = 10, comment_depth: Optional[int] = 1) -> List[Dict[str, Any]]:
    """
    Fetches and processes comments from a submission using an efficient method.

    Args:
        submission: The PRAW submission object.
        sort_order (str): The order to sort comments by ('best', 'top', 'new', 'controversial', 'old', 'score').
        num_comments (int): The number of top-level comments to retrieve.
        comment_depth (Optional[int]): The maximum depth of comment replies to retrieve (0-indexed).
                                       None means process to full depth allowed by _process_comment.

    Returns:
        list: A list of dictionaries, where each dictionary represents a comment and its replies.
    
    Raises:
        CommentRetrievalError: If comments cannot be retrieved due to API issues.
        APIAuthenticationError: If authentication fails during comment retrieval.
    """
    logger.info(f"Fetching up to {num_comments} comments for post ID {submission.id}, sorted by '{sort_order}', with depth {comment_depth}.")

    # Map 'score' to a PRAW-compatible sort order for initial fetching.
    # PRAW's 'top' sort is by score. 'best' is Reddit's default algorithm.
    # Other valid PRAW sorts: 'new', 'controversial', 'old', 'q&a'
    actual_praw_sort = sort_order.lower()
    if actual_praw_sort == 'score':
        actual_praw_sort = 'top'
    
    valid_praw_sorts = ['best', 'top', 'new', 'controversial', 'old', 'q&a']
    if actual_praw_sort not in valid_praw_sorts:
        logger.warning(f"Invalid comment sort_order '{sort_order}'. Defaulting to 'best'.")
        actual_praw_sort = 'best'

    try:
        submission.comment_sort = actual_praw_sort
        # Set a limit slightly higher than num_comments to account for potential MoreComments objects
        # or non-Comment items in the initial list from PRAW, ensuring we likely get enough.
        # PRAW's comment_limit influences the initial fetch size.
        submission.comment_limit = num_comments * 2 if num_comments else 20 # Fetch a bit more to be safe
        
        comments_data_list = []
        processed_top_level_count = 0

        # Iterate through the comments provided by PRAW, respecting comment_limit and comment_sort
        for top_level_comment in submission.comments:
            if processed_top_level_count >= num_comments:
                break  # Stop once we have processed enough top-level comments

            if isinstance(top_level_comment, praw.models.Comment):
                # _process_comment will handle fetching replies for this specific comment
                # down to the specified comment_depth.
                comment_data = _process_comment(
                    top_level_comment,
                    depth=0,  # current_depth for top-level comment
                    max_depth=comment_depth
                )
                if comment_data:  # Ensure comment wasn't deleted or an issue
                    comments_data_list.append(comment_data)
                    processed_top_level_count += 1
            elif isinstance(top_level_comment, praw.models.MoreComments):
                logger.debug(f"Skipping MoreComments object {top_level_comment.id} at top level during initial scan.")
                # We are not expanding these top-level MoreComments here to maintain efficiency.
                # The comment_limit is set higher to try and get enough actual comments initially.
            else:
                logger.warning(f"Encountered an unexpected object type in submission.comments: {type(top_level_comment)}")

        # If the original sort_order was 'score', and we used 'top' for PRAW's initial sort,
        # it's already sorted by score. If another PRAW sort was used (e.g. 'best' due to invalid input),
        # and the user specifically asked for 'score', we could re-sort.
        # However, PRAW's 'top' is generally the most direct way to get score-sorted comments.
        # For now, we'll assume the actual_praw_sort ('top' or 'best', etc.) is sufficient.
        # If a strict re-sort by 'score' of the fetched list is needed:
        if sort_order.lower() == 'score':
             # Ensure we sort the *collected* list if the initial sort wasn't 'top'
             # or if we want to be absolutely sure after processing.
            if actual_praw_sort != 'top': # Or just always re-sort if sort_order == 'score'
                logger.info(f"Re-sorting the fetched {len(comments_data_list)} comments by score.")
                comments_data_list.sort(key=lambda c: c.get('score', 0), reverse=True)
            # Ensure the list is trimmed to num_comments if it became longer due to initial over-fetching
            comments_data_list = comments_data_list[:num_comments]


        logger.info(f"Successfully fetched and processed {len(comments_data_list)} top-level comments for post ID: {submission.id}.")
        return comments_data_list

    except praw.exceptions.PRAWException as e:
        logger.error(f"PRAWException in fetch_comments_data for post {submission.id}: {e}", exc_info=True)
        if "401" in str(e) or "403" in str(e):
            raise APIAuthenticationError(f"Authentication error fetching comments for post {submission.id}.") from e
        elif "404" in str(e) or "not found" in str(e).lower():
             raise CommentRetrievalError(f"Post {submission.id} comments not found or post became inaccessible (404).") from e
        raise CommentRetrievalError(f"Failed to fetch comments for post {submission.id} due to API error: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error in fetch_comments_data for post {submission.id}: {e}", exc_info=True)
        raise CommentRetrievalError(f"An unexpected error occurred while fetching comments for post {submission.id}: {e}") from e

# ... (extract_media_info remains the same)
def extract_media_info(submission: praw.models.Submission) -> List[Dict[str, Any]]:
    """Extracts structured media information from a PRAW submission object.

    Handles various media types like direct images/videos, Reddit-hosted media,
    image galleries, and embeds (like YouTube).

    Args:
        submission: The PRAW Submission object.

    Returns:
        A list of dictionaries, each representing a structured media item.
    """
    structured_media: List[Dict[str, Any]] = [] 
    logger.debug(f"Extracting media info for submission {submission.id}")
    
    try: # Wrap extraction logic in case of unexpected attribute errors
        # 1. Galleries
        if hasattr(submission, 'is_gallery') and submission.is_gallery and hasattr(submission, 'media_metadata') and submission.media_metadata:
            logger.debug(f"Processing as gallery post: {submission.id}")
            for media_id, item in submission.media_metadata.items():
                if item.get('e') == 'Image' and item.get('s'):
                    structured_media.append({
                        'type': 'image_gallery_item',
                        'id': media_id,
                        'url': item['s'].get('u'),
                        'width': item['s'].get('x'),
                        'height': item['s'].get('y'),
                        'mimetype': item.get('m')
                    })
                elif item.get('e') == 'Video' and item.get('s'):
                     structured_media.append({
                        'type': 'animated_gallery_item',
                        'id': media_id,
                        'url': item['s'].get('mp4', item['s'].get('gif')),
                        'width': item['s'].get('x'),
                        'height': item['s'].get('y'),
                        'mimetype': item.get('m')
                    })
            if structured_media:
                logger.info(f"Extracted {len(structured_media)} items from gallery for post {submission.id}")
                return structured_media # Galleries are usually exclusive

        # 2. Reddit Video/GIF
        elif submission.is_video and hasattr(submission, 'media') and submission.media and 'reddit_video' in submission.media:
            logger.debug(f"Processing as Reddit video post: {submission.id}")
            reddit_video = submission.media['reddit_video']
            structured_media.append({
                'type': 'reddit_video',
                'url': reddit_video.get('fallback_url'),
                'hls_url': reddit_video.get('hls_url'),
                'dash_url': reddit_video.get('dash_url'),
                'duration_seconds': reddit_video.get('duration'),
                'width': reddit_video.get('width'),
                'height': reddit_video.get('height'),
                'is_gif': reddit_video.get('is_gif'),
                'transcoding_status': reddit_video.get('transcoding_status')
            })
            logger.info(f"Extracted Reddit video info for post {submission.id}")
            return structured_media # Usually exclusive
            
        # 3. Direct Image / Link with Preview
        elif hasattr(submission, 'preview') and submission.preview and 'images' in submission.preview and submission.preview['images']:
            logger.debug(f"Processing post with preview images: {submission.id}")
            if submission.domain in ['i.redd.it', 'i.imgur.com']: 
                source_image = submission.preview['images'][0]['source']
                structured_media.append({
                    'type': 'image',
                    'url': submission.url,
                    'width': source_image.get('width'),
                    'height': source_image.get('height')
                })
                logger.info(f"Extracted direct image info for post {submission.id}")
                return structured_media # Treat as exclusive
            elif not submission.is_self and submission.url and not submission.is_video:
                image_extensions = ['.jpg', '.jpeg', '.png', '.gif']
                if any(submission.url.lower().endswith(ext) for ext in image_extensions) and not submission.domain == 'v.redd.it':
                     source_image = submission.preview['images'][0]['source']
                     structured_media.append({
                        'type': 'image_link',
                        'url': submission.url,
                        'width': source_image.get('width'),
                        'height': source_image.get('height'),
                        'preview_url': source_image.get('url')
                    })
                     logger.info(f"Extracted image link with preview for post {submission.id}")
                     # This might coexist with embeds, so don't return yet
        
        # 4. Embedded Media (e.g., YouTube from oEmbed)
        if hasattr(submission, 'secure_media') and submission.secure_media and 'oembed' in submission.secure_media:
            logger.debug(f"Processing oEmbed media for post: {submission.id}")
            oembed = submission.secure_media['oembed']
            if oembed.get('type') == 'video' and oembed.get('provider_name') == 'YouTube':
                structured_media.append({
                    'type': 'youtube_video_embed',
                    'url': oembed.get('url'),
                    'html_embed': oembed.get('html'),
                    'thumbnail_url': oembed.get('thumbnail_url'),
                    'title': oembed.get('title'),
                    'author_name': oembed.get('author_name'),
                    'provider_name': oembed.get('provider_name')
                })
                logger.info(f"Extracted YouTube embed info for post {submission.id}")
                return structured_media # Treat embed as primary/exclusive if found
            # Add checks for other oEmbed providers if needed

        # 5. Fallback: External Image Link (if not caught by other types)
        if not structured_media and not submission.is_self and not submission.is_video and not submission.is_gallery:
            image_extensions = ['.jpg', '.jpeg', '.png', '.gif']
            if any(submission.url.lower().endswith(ext) for ext in image_extensions) and \
               not submission.domain in ['i.redd.it', 'v.redd.it']:
                 logger.debug(f"Processing as external image link (fallback): {submission.id}")
                 structured_media.append({
                    'type': 'external_image_link',
                    'url': submission.url
                })
                 logger.info(f"Extracted external image link (fallback) for post {submission.id}")
                 # Don't return yet, could still have an embed processed above
                 
        if not structured_media:
             logger.debug(f"No specific media type identified for post {submission.id}. It might be a text post or a simple link.")
             
    except Exception as e:
        logger.error(f"Error extracting media info for submission {submission.id}: {e}", exc_info=True)
        # Return empty list on error, allows main processing to continue

    return structured_media # Return the list directly

# --- Test Block ---
if __name__ == '__main__':
    # Setup basic logging for testing this module
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    from auth import initialize_reddit_client
    from url_processor import extract_post_id, validate_reddit_url
    from output_formatter import format_data_as_json, save_json_to_file, generate_filename
    import json

    media_test_urls = {
        "text_only": "https://www.reddit.com/r/ADHD/comments/1kg08k0/whats_a_weird_little_adhd_trick_that_actually/",
        "direct_image": "https://www.reddit.com/r/eatsandwiches/comments/k2mnz4/french_fuck_off_sandwich/",
        "reddit_video": "https://www.reddit.com/r/funnyvideos/comments/1h6fi6k/i_will_never_not_love_this_video/",
        "image_gallery": "https://www.reddit.com/r/pics/comments/1kcoxi2/empty_seats_for_trump_at_the_university_of/",
        "youtube_embed": "https://www.reddit.com/r/StableDiffusion/comments/1kdlwo7/reviving_2pac_and_michael_jackson_with_rvc_flux/",
        "not_found_post": "https://www.reddit.com/r/testingground/comments/nonexistent123/" # Example of a non-existent post
    }
    
    url_to_inspect = media_test_urls["text_only"] 
    # url_to_inspect = media_test_urls["direct_image"]
    # url_to_inspect = media_test_urls["reddit_video"]
    # url_to_inspect = media_test_urls["image_gallery"]
    # url_to_inspect = media_test_urls["youtube_embed"]
    # url_to_inspect = media_test_urls["not_found_post"] # Test error handling

    logger.info(f"--- Testing with URL: {url_to_inspect} ---")

    if not validate_reddit_url(url_to_inspect):
        logger.error(f"URL failed validation: {url_to_inspect}")
        exit()

    post_id = extract_post_id(url_to_inspect)
    if not post_id:
        logger.error(f"Could not extract post ID from: {url_to_inspect}")
        exit()
    
    logger.info(f"Extracted Post ID: {post_id}")

    try:
        reddit = initialize_reddit_client() # This can also raise ConfigError
        logger.info("Reddit client initialized.")

        # Test fetch_post_data
        logger.info(f"Fetching post data for {post_id}...")
        post_data = fetch_post_data(reddit, post_id, include_raw_media_details=True) # Example: include raw details for testing
        
        if post_data:
            logger.info(f"Post Title: {post_data['title']}")
            logger.info(f"Author: {post_data['author']}")
            logger.info(f"Subreddit: {post_data['subreddit']}")
            logger.info(f"Score: {post_data['score']}")
            logger.info(f"Selftext (excerpt): {post_data['selftext'][:100] if post_data['selftext'] else 'N/A'}...")
            logger.info(f"Media Info (structured list): {json.dumps(post_data.get('media_info', 'N/A'), indent=2)}")
            
            # Test fetch_comments_data
            # First, get the submission object, as fetch_comments_data now requires it.
            logger.info(f"Re-fetching submission object for comment processing: {post_id}")
            submission_obj = reddit.submission(id=post_id) # Fetch the submission object
            
            logger.info(f"Fetching comments for {post_id} (num_comments 5, sort_order 'best', comment_depth 1)...")
            # Call fetch_comments_data with the submission object and new parameter names
            comments_data = fetch_comments_data(
                submission_obj, 
                sort_order='best', 
                num_comments=5, 
                comment_depth=1
            )
            logger.info(f"Fetched {len(comments_data)} top-level comments.")
            # for i, comment in enumerate(comments_data):
            #     logger.info(f"  Comment {i+1} by {comment['author']}: {comment['body'][:50]}...")
            #     if comment['replies']:
            #         logger.info(f"    - Has {len(comment['replies'])} replies at depth 1")

            # --- Formatting and Saving ---
            final_data_structure = format_data_as_json(post_data, comments_data) # Use comments_data
            output_filename = generate_filename(post_data['id'], post_data['title'])
            
            logger.info(f"Attempting to save to: {output_filename}")
            save_json_to_file(final_data_structure, output_filename)
            logger.info(f"Successfully saved data to {output_filename}")

            # print("\n--- Raw Post Data (for media inspection) ---")
            # print(f"Submission URL: {post_data.get('url')}")
            # print(f"Is Gallery: {post_data.get('is_gallery', 'N/A')}")
            # print(f"Media: {json.dumps(post_data.get('_raw_media'), indent=2)}")
            # print(f"Media Embed: {json.dumps(post_data.get('_raw_media_embed'), indent=2)}")
            # print(f"Secure Media: {json.dumps(post_data.get('_raw_secure_media'), indent=2)}")
            # print(f"Secure Media Embed: {json.dumps(post_data.get('_raw_secure_media_embed'), indent=2)}")
            # print(f"Gallery Data: {json.dumps(post_data.get('_raw_gallery_data'), indent=2)}")
            # print(f"Media Metadata: {json.dumps(post_data.get('_raw_media_metadata'), indent=2)}")
            # print("---------------------------------------------")
        else:
            logger.warning(f"No post data returned for {post_id}")

    except APIAuthenticationError as e:
        logger.error(f"API Authentication Error: {e}")
    except PostRetrievalError as e:
        logger.error(f"Post Retrieval Error: {e}")
    except CommentRetrievalError as e:
        logger.error(f"Comment Retrieval Error: {e}")
    except OutputError as e: # Assuming output_formatter might raise this
        logger.error(f"Output Formatting/Saving Error: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred in the test block: {e}", exc_info=True)

    logger.info(f"--- Test finished for URL: {url_to_inspect} ---") 