import json
import re
from datetime import datetime, timezone
import logging
from typing import Dict, List, Any, Optional # For type hints
from error_handler import OutputError

logger = logging.getLogger(__name__)

# Define the current version of the extractor
EXTRACTOR_VERSION = "0.1.0"

def _process_comment_timestamps(comments: List[Dict[str, Any]]):
    """Recursively processes a list of comment dictionaries to convert UTC timestamps.
    
    Modifies the list of dictionaries in-place, adding an 'created_iso' field
    based on the 'created_utc' field.

    Args:
        comments: A list of comment dictionaries, potentially nested via a 'replies' key.
    """
    for comment in comments:
        if comment and isinstance(comment, dict):
            iso_timestamp = None # Default to None
            if 'created_utc' in comment and comment['created_utc'] is not None:
                try:
                    iso_timestamp = datetime.fromtimestamp(comment['created_utc'], timezone.utc).isoformat()
                except (TypeError, ValueError) as e:
                    logger.warning(f"Could not convert timestamp {comment['created_utc']} for comment ID {comment.get('id', 'N/A')}: {e}")
                    # iso_timestamp remains None
            
            comment['created_iso'] = iso_timestamp # Always add the key
            
            if 'replies' in comment and isinstance(comment['replies'], list):
                _process_comment_timestamps(comment['replies'])
            # No specific handling needed for 'replies': '[Max depth reached]' here regarding timestamps

def format_data_as_json(post_data: Dict[str, Any], comments_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Structures the final output data including metadata and versioning.

    Adds ISO timestamps to post and comment data based on their UTC timestamps.

    Args:
        post_data: Dictionary containing the fetched post details.
        comments_data: List of dictionaries representing the fetched comments.

    Returns:
        A dictionary representing the final structured JSON output.
        
    Raises:
        OutputError: If an unexpected error occurs during formatting.
    """
    logger.info(f"Formatting data for post ID: {post_data.get('id', 'N/A')}")
    try:
        iso_timestamp_post = None # Default to None
        if 'created_utc' in post_data and post_data['created_utc'] is not None:
            try:
                iso_timestamp_post = datetime.fromtimestamp(post_data['created_utc'], timezone.utc).isoformat()
            except (TypeError, ValueError) as e:
                logger.warning(f"Could not convert post timestamp {post_data['created_utc']} for post ID {post_data.get('id', 'N/A')}: {e}")
        post_data['created_iso'] = iso_timestamp_post # Always add the key
        
        if comments_data:
            _process_comment_timestamps(comments_data)

        output_structure = {
            'extractor_version': EXTRACTOR_VERSION,
            'extraction_timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'source_url': post_data.get('permalink', post_data.get('url')), # Prefer permalink
            'post_details': post_data,
            'comments': comments_data
        }
        logger.info(f"Data formatting complete for post ID: {post_data.get('id', 'N/A')}")
        return output_structure
    except Exception as e:
        logger.error(f"Unexpected error during data formatting for post ID {post_data.get('id', 'N/A')}: {e}", exc_info=True)
        raise OutputError(f"Failed to format data due to an unexpected error: {e}") from e

def generate_filename(post_id: str, post_title: Optional[str]) -> str:
    """Generates a sanitized filename from the post ID and title.
    
    Removes potentially invalid characters from the title and truncates it.
    Provides a fallback name if title processing fails.

    Args:
        post_id: The Reddit post ID.
        post_title: The title of the Reddit post.

    Returns:
        A sanitized string suitable for use as a filename (including .json extension).
    """
    logger.debug(f"Generating filename for post ID: {post_id}, title: {post_title[:50] if post_title else 'N/A'}...")
    try:
        if not post_title:
            sanitized_title = "untitled"
        else:
            # Step 1: Replace invalid characters and sequences of whitespace with a single underscore
            temp_title = re.sub(r'[\\/:*?"<>|\s]+', '_', post_title.strip())
            # Step 2: Remove any remaining characters that are not alphanumeric or underscore
            sanitized_title = re.sub(r'[^\w\d_]+', '', temp_title)
            # Step 3: Collapse multiple underscores that might have been created
            sanitized_title = re.sub(r'_{2,}', '_', sanitized_title).strip('_')
            
            # Step 4: If the result is empty after sanitization, use "untitled"
            if not sanitized_title:
                sanitized_title = "untitled"
        
        max_title_len = 50
        truncated_title = sanitized_title[:max_title_len]
        
        filename = f"{post_id}_{truncated_title}.json"
        logger.info(f"Generated filename: {filename}")
        return filename
    except Exception as e:
        default_filename = f"{post_id}_extraction_error.json" 
        logger.error(f"Error generating filename for ID {post_id}, title '{post_title}': {e}. Defaulting to '{default_filename}'", exc_info=True)
        return default_filename

def save_json_to_file(data: Dict[str, Any], filename: str):
    """Saves the provided data dictionary to a JSON file.

    Args:
        data: The dictionary containing the data to save.
        filename: The path to the file where the data should be saved.

    Raises:
        OutputError: If any error occurs during file writing or JSON serialization.
    """
    logger.info(f"Attempting to save data to file: {filename}")
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info(f"Successfully saved data to {filename}")
    except IOError as e:
        logger.error(f"IOError saving data to {filename}: {e}", exc_info=True)
        raise OutputError(f"Could not write to file {filename}: {e}") from e
    except TypeError as e: # For issues with non-serializable data if not caught earlier
        logger.error(f"TypeError during JSON serialization for {filename}: {e}", exc_info=True)
        raise OutputError(f"Data for {filename} was not JSON serializable: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error saving JSON to {filename}: {e}", exc_info=True)
        raise OutputError(f"An unexpected error occurred while saving to {filename}: {e}") from e

# --- Test Block (Optional - can be kept or simplified) ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger.info("--- Testing Output Formatter --- ")

    # Mock data for testing
    mock_post = {
        'id': 'testpost123',
        'title': 'This is a Test Post! With Punctuation & Stuff?*~',
        'author': 'testuser',
        'created_utc': 1678886400, # Example timestamp
        'selftext': 'Hello world.',
        'url': 'https://reddit.com/r/test/comments/testpost123'
    }
    mock_comments = [
        {
            'id': 'c1', 'author': 'user1', 'body': 'First comment!', 'created_utc': 1678886500,
            'replies': [
                {
                    'id': 'c1_r1', 'author': 'user2', 'body': 'Reply to first!', 'created_utc': 1678886600,
                    'replies': []
                }
            ]
        },
        {
            'id': 'c2', 'author': 'user3', 'body': 'Second comment with no replies.', 'created_utc': 1678886700,
            'replies': '[Max depth reached]' # Test this case
        },
        {
            'id': 'c3', 'author': 'user4', 'body': 'Comment with invalid UTC', 'created_utc': "not a timestamp",
             'replies': []
        }
    ]

    try:
        logger.info("1. Testing generate_filename...")
        fname = generate_filename(mock_post['id'], mock_post['title'])
        logger.info(f"Generated filename: {fname}")
        assert fname == "testpost123_This_is_a_Test_Post_With_Punctuation_Stuff.json", f"Unexpected filename: {fname}"
        
        fname_empty_title = generate_filename("post456", "")
        logger.info(f"Generated filename for empty title: {fname_empty_title}")
        assert fname_empty_title == "post456_untitled.json", f"Unexpected filename for empty: {fname_empty_title}"

        fname_only_symbols = generate_filename("post789", "*&^%")
        logger.info(f"Generated filename for symbols only title: {fname_only_symbols}")
        assert fname_only_symbols == "post789_untitled.json", f"Unexpected filename for symbols: {fname_only_symbols}"

        logger.info("2. Testing format_data_as_json...")
        formatted_data = format_data_as_json(mock_post, mock_comments)
        assert 'extractor_version' in formatted_data
        assert 'extraction_timestamp_utc' in formatted_data
        assert 'post_details' in formatted_data
        assert 'comments' in formatted_data
        assert formatted_data['post_details']['created_iso'] is not None
        assert formatted_data['comments'][0]['created_iso'] is not None
        assert formatted_data['comments'][0]['replies'][0]['created_iso'] is not None
        assert formatted_data['comments'][2]['created_iso'] is None # For the invalid timestamp
        logger.info("JSON data formatted. Checking structure and timestamps.")
        # print(json.dumps(formatted_data, indent=2))

        logger.info("3. Testing save_json_to_file...")
        test_output_filename = "test_output_formatter_output.json"
        save_json_to_file(formatted_data, test_output_filename)
        logger.info(f"Data saved to {test_output_filename}. Please verify its contents.")
        # Clean up test file (optional)
        # import os
        # os.remove(test_output_filename)

        logger.info("Output formatter tests completed successfully.")

    except OutputError as e:
        logger.error(f"OutputError during test: {e}")
    except AssertionError as e:
        logger.error(f"AssertionError during test: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during output_formatter test: {e}", exc_info=True)
    finally:
        logger.info("--- Output Formatter Test Finished ---") 