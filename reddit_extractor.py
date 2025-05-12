# Main script for the Reddit Content Extractor
import argparse
import sys
import logging
import json
from typing import Any, Optional, List, Dict # For type hints

# Import functions from other modules
from url_processor import validate_reddit_url, extract_post_id
from auth import initialize_reddit_client
from data_retriever import fetch_post_data, fetch_comments_data
from output_formatter import format_data_as_json, save_json_to_file, generate_filename
from error_handler import (
    RedditExtractorError, URLValidationError, APIAuthenticationError,
    PostRetrievalError, CommentRetrievalError, OutputError, ConfigError,
    format_user_error_message
)
from media_downloader import download_media_item # Import the new function

# Import for OS path operations (used for creating media folder)
import os

# Import for URL parsing
from urllib.parse import urlparse

# --- Logging Setup ---
logger = logging.getLogger(__name__) # Logger for this main script

# --- Interactive Prompt Functions --- #
def prompt_for_url() -> str:
    """Prompts user for a valid Reddit URL."""
    while True:
        url = input("Please enter the Reddit post URL: ").strip()
        if not url:
            print("Error: URL cannot be empty.")
            continue
        if validate_reddit_url(url):
            return url
        else:
            print("Error: Invalid Reddit URL format. Please try again.")

def prompt_for_comment_limit() -> Optional[int]:
    """Prompts user for comment retrieval preference.
    Returns: int (number of comments), 0 (no comments), or None (all comments).
    """
    while True:
        response = input("Fetch comments? [N | all | no] (default: all): ").strip().lower()
        if not response or response == 'all':
            return None
        elif response == 'no':
            return 0
        else:
            try:
                count = int(response)
                if count >= 0:
                    return count
                else:
                    print("Error: Please enter a non-negative number.")
            except ValueError:
                print("Error: Invalid input. Please enter a number (e.g., 50), 'all', or 'no'.")

def prompt_for_sort_order() -> str:
    """Prompts user for comment sort order."""
    valid_sorts = ['best', 'top', 'new', 'controversial', 'old', 'q&a']
    prompt_text = f"Sort comments by? [{' | '.join(valid_sorts)}] (default: best): "
    while True:
        response = input(prompt_text).strip().lower()
        if not response:
            return 'best'
        elif response in valid_sorts:
            return response
        else:
            print(f"Error: Invalid sort order. Please choose from: {valid_sorts}")

def prompt_for_depth_limit() -> Optional[int]:
    """Prompts user for comment depth limit.
    Returns: int or None (for all depths).
    """
    while True:
        response = input("Maximum comment reply depth? [N | all] (default: all): ").strip().lower()
        if not response or response == 'all':
            return None
        else:
            try:
                depth = int(response)
                if depth >= 0:
                    return depth
                else:
                    print("Error: Please enter a non-negative number.")
            except ValueError:
                print("Error: Invalid input. Please enter a number (e.g., 5) or 'all'.")

def prompt_for_output_file() -> Optional[str]:
    """Prompts user for an optional output filename."""
    response = input("Output filename (leave blank to auto-generate): ").strip()
    return response if response else None

def prompt_for_print_to_console() -> bool:
    """Asks user if they want to print JSON to console instead of saving."""
    while True:
        response = input("Print JSON to console instead of saving? [y/N] (default: N): ").strip().lower()
        if not response or response == 'n':
            return False
        elif response == 'y':
            return True
        else:
            print("Error: Please enter 'y' or 'n'.")

def prompt_for_raw_media_details() -> bool:
    """Asks user if they want to include raw media details."""
    while True:
        response = input("Include verbose raw media details (e.g., all image resolutions, extensive metadata) in JSON? (This can significantly increase file size) [y/N] (default: N): ").strip().lower()
        if not response or response == 'n':
            return False
        elif response == 'y':
            return True
        else:
            print("Error: Please enter 'y' or 'n'.")

# --- New Media Download Prompt Functions ---

def prompt_media_download_confirmation() -> bool:
    """Asks user if they want to download media from the main post."""
    while True:
        response = input("Media detected in the main post. Do you want to download it? [y/N] (default: N): ").strip().lower()
        if not response or response == 'n':
            return False
        elif response == 'y':
            return True
        else:
            print("Error: Please enter 'y' or 'n'.")

def prompt_media_download_scope() -> str:
    """Asks user for the scope of media download."""
    print("Download media from:")
    print("  1. Main post only")
    print("  2. Comments only")
    print("  3. Main post and Comments")
    while True:
        response = input("Please choose an option (1, 2, or 3) (default: 1): ").strip()
        if not response or response == '1':
            return 'post'
        elif response == '2':
            return 'comments'
        elif response == '3':
            return 'both'
        else:
            print("Error: Invalid option. Please enter 1, 2, or 3.")

# --- New Helper to Extract Media URLs ---
def _get_post_media_urls(post_data: Dict[str, Any]) -> List[str]:
    """Extracts downloadable media URLs from the post_data's media_info."""
    media_urls = []
    if not post_data or not isinstance(post_data.get('media_info'), list):
        return media_urls

    for item in post_data['media_info']:
        if not isinstance(item, dict):
            continue

        primary_url = item.get('url')
        item_type = item.get('type')
        url_to_add = None

        if item_type == 'reddit_video':
            # Check primary URL for direct MP4/GIF
            if primary_url and isinstance(primary_url, str) and primary_url.split('?')[0].endswith(('.mp4', '.gif')):
                url_to_add = primary_url
                logger.debug(f"Reddit video: Using primary URL: {url_to_add}")
            else:
                # If primary URL is not direct, check fallback URL
                fallback_url = item.get('fallback_url')
                if fallback_url and isinstance(fallback_url, str) and fallback_url.split('?')[0].endswith(('.mp4', '.gif')):
                    url_to_add = fallback_url
                    logger.debug(f"Reddit video: Using fallback URL: {url_to_add}")
                else:
                    logger.debug(f"Reddit video: Neither primary URL ('{primary_url}') nor fallback URL ('{fallback_url}') is a direct MP4/GIF. HLS/DASH might be available: {item.get('hls_url')}")
        
        elif primary_url and isinstance(primary_url, str):
            # For other types (images, direct links from galleries, etc.)
            # Basic check: ensure URL is not None and seems like a file (heuristic)
            # Avoid trying to download HTML pages or generic provider URLs if possible.
            is_youtube = 'youtube.com/watch' in primary_url or 'youtu.be/' in primary_url
            path_part = primary_url.split('?')[0]
            is_direct_media_link = path_part.endswith(('.jpg', '.jpeg', '.png', '.gif', '.mp4'))

            if not is_youtube and is_direct_media_link:
                url_to_add = primary_url
                logger.debug(f"Non-Reddit video/image: Using URL: {url_to_add} of type {item_type}")
            elif is_youtube:
                logger.debug(f"Skipping YouTube URL (requires youtube-dl or similar): {primary_url}")
            else:
                logger.debug(f"Skipping potentially non-direct media URL: {primary_url} of type {item_type}")

        if url_to_add and url_to_add not in media_urls: # Avoid duplicates
            media_urls.append(url_to_add)

    logger.info(f"Found {len(media_urls)} potential media URLs in post data: {media_urls}")
    return media_urls

# --- New Helper to Extract Comment Media URLs (Targeted) ---
def _get_comment_media_urls(comments_data: List[Dict[str, Any]]) -> List[str]:
    """Recursively extracts direct Reddit media URLs (i.redd.it, preview.redd.it)
    from a list of comments and their replies."""
    found_urls = set() # Use a set to store URLs to ensure uniqueness

    def find_urls_in_comment_list(comment_list: List[Dict[str, Any]]):
        for comment in comment_list:
            if isinstance(comment, dict) and isinstance(comment.get('body'), str):
                body_text = comment['body']
                logger.debug(f"Processing comment body for media URLs: {body_text[:200]}...")
                words = body_text.split() # Split by space to find potential URLs
                for word in words:
                    logger.debug(f"Checking word from comment: {word}")
                    # Ensure the word is a full URL, not just a part of one.
                    # A simple check is if it contains '://' and the target domain.
                    if (word.startswith("https://preview.redd.it/") or word.startswith("https://i.redd.it/")) and "://" in word :
                        logger.debug(f"Potential Reddit media URL found: {word}")
                        
                        # Parse the URL to isolate the path for extension checking
                        try:
                            parsed_url = urlparse(word)
                            path_before_query = parsed_url.path
                            logger.debug(f"Parsed path for extension check: {path_before_query}")

                            if path_before_query.endswith( ('.jpeg', '.jpg', '.png', '.gif')):
                                # Add the original word (full URL with query params)
                                logger.info(f"Adding Reddit media URL (with query params) from comment to download list: {word}")
                                found_urls.add(word)
                            else:
                                logger.debug(f"URL path {path_before_query} did not pass extension check ('.jpeg', '.jpg', '.png', '.gif'). Original word: {word}")
                        except Exception as e:
                            logger.error(f"Error parsing URL '{word}' for comment media: {e}")
            
            # Recursively check replies
            if isinstance(comment.get('replies'), list):
                find_urls_in_comment_list(comment['replies'])

    if isinstance(comments_data, list):
        find_urls_in_comment_list(comments_data)
    
    logger.info(f"Found {len(found_urls)} potential media URLs in comments: {list(found_urls)}")
    return list(found_urls)

# --- Argument Parsing --- #
def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments or initiates interactive mode.
    
    Sets up logging based on provided arguments (--verbose, --log-file).
    If no URL is provided via arguments (and args aren't just logging ones),
    it enters interactive mode to gather necessary parameters.
    Calculates and adds the final 'comment_limit' attribute to the args object.

    Returns:
        argparse.Namespace: An object containing all processed arguments/parameters,
                            ready to be used by the main script logic.
    """
    parser = argparse.ArgumentParser(
        description="Extract content (post and comments) from Reddit posts.",
        epilog="Example: python reddit_extractor.py --url <reddit_post_url> --comments 50 --sort top -o my_output.json"
    )
    parser.add_argument(
        '--url', 
        type=str, 
        help='URL of the Reddit post to extract. Required unless running interactively.'
    )
    comment_group = parser.add_mutually_exclusive_group()
    comment_group.add_argument(
        '--comments', 
        type=int, 
        metavar='N', 
        help='Number of top-level comments to retrieve. Provide 0 for none.'
    )
    comment_group.add_argument(
        '--all-comments', 
        action='store_true', 
        help='Retrieve all top-level comments. This is the default if no specific comment option is chosen in CLI mode.'
    )
    comment_group.add_argument(
        '--no-comments', 
        action='store_true', 
        help='Do not retrieve any comments.'
    )
    parser.add_argument(
        '--sort', 
        type=str, 
        choices=['best', 'top', 'new', 'controversial', 'old', 'q&a'],
        default='best', 
        help='Sort order for comments (default: %(default)s).'
    )
    parser.add_argument(
        '--depth', 
        type=int, 
        metavar='D',
        default=None,
        help='Maximum depth of comment replies (default: all depths).'
    )
    parser.add_argument(
        '--output', '-o', 
        type=str, 
        help='Output filename. If omitted, generates based on post ID/title.'
    )
    parser.add_argument(
        '--print', 
        action='store_true', 
        help='Print the final JSON to the console instead of saving to a file.'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging to the console (DEBUG level).'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        default=None,
        help='Path to a file for logging output (INFO level by default, DEBUG if -v is also used).'
    )
    parser.add_argument(
        '--include-raw-media',
        action='store_true',
        default=False, # Explicitly set default, though store_true defaults to False
        help='Include extensive raw media metadata from PRAW in the JSON output (e.g., all image resolutions). This can significantly increase file size. Defaults to not included.'
    )

    args = parser.parse_args()
    
    # Setup Logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
    handlers = []
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))
    handlers.append(console_handler)
    if args.log_file:
        try:
            file_handler = logging.FileHandler(args.log_file, mode='a')
            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(log_format))
            handlers.append(file_handler)
        except Exception as e:
            print(f"Warning: Could not set up log file at '{args.log_file}': {e}", file=sys.stderr)
    logging.basicConfig(level=log_level, format=log_format, handlers=handlers, force=True) # force=True to override initial basicConfig
    
    logger.debug(f"Raw command line arguments: {sys.argv}")
    logger.debug(f"Parsed arguments (initial): {args}")

    # Determine execution mode
    # Interactive if no URL, or if only logging/print args are present without a URL
    is_cli_mode = bool(args.url)
    args.interactive_mode = not is_cli_mode # Add interactive_mode flag

    if not is_cli_mode:
        print("--- Reddit Content Extractor: Interactive Mode ---")
        args.url = prompt_for_url()
        comment_limit_interactive = prompt_for_comment_limit()
        if comment_limit_interactive is None:
            args.all_comments = True
        elif comment_limit_interactive == 0:
            args.no_comments = True
        else:
            args.comments = comment_limit_interactive
        
        if not args.no_comments: # Only ask for sort and depth if fetching comments
            args.sort = prompt_for_sort_order()
            args.depth = prompt_for_depth_limit()
        
        args.output = prompt_for_output_file()
        args.print = prompt_for_print_to_console()
        args.include_raw_media = prompt_for_raw_media_details()

    # Determine final comment fetch count based on CLI or interactive input
    final_comment_limit: Optional[int]
    if args.no_comments:
        args.comment_limit = 0
    elif args.comments is not None: 
        if args.comments < 0:
            msg = "argument --comments: value must be a non-negative integer."
            logger.error(msg)
            parser.error(msg)
        args.comment_limit = args.comments
    elif args.all_comments:
         args.comment_limit = None
    elif not hasattr(args, 'comment_limit'): # If not set by interactive and no flags were used in CLI
        if args.url: # If URL was provided (CLI mode), default to all
            logger.debug("Defaulting comment_limit to None (all comments) as no specific option was chosen in CLI mode.")
            args.comment_limit = None
        # If URL was not provided, interactive mode should have set it. This is a fallback.
        elif not args.no_comments:
            logger.warning("Comment limit not explicitly set, defaulting to None (all).")
            args.comment_limit = None 
        else: # Should have been set to 0 if args.no_comments was true
            args.comment_limit = 0 
    
    logger.debug(f"Final resolved arguments: {args}")
    return args

# --- Main Execution Logic --- #
def main() -> int:
    """Main execution function for the Reddit Extractor.

    Parses arguments (or runs interactive mode), sets up logging, 
    orchestrates the data fetching and processing steps, handles output,
    and manages errors.

    Returns:
        int: 0 on success, 1 on failure.
    """
    # Basic logging config first, might be overridden by parse_arguments
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s [%(name)s] %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
    
    args = None # Define args here to ensure it's accessible in the final except block
    exit_code = 0
    try:
        args = parse_arguments()

        logger.info("--- Reddit Content Extractor Initializing ---")
        logger.info(f"Target URL: {args.url}")
        logger.info(f"Comment Limit: {args.comment_limit}, Sort: {args.sort}, Depth: {args.depth}")
        logger.info(f"Output to file: {args.output if args.output else 'Auto-generated'}, Print to console: {args.print}")
        logger.info("---------------------------------------------")

        if not validate_reddit_url(args.url):
            # This case should ideally be caught by interactive prompt or arg parser for format,
            # but as a final check.
            raise URLValidationError(f"Invalid Reddit URL provided: {args.url}")
        logger.info(f"URL '{args.url}' validated successfully.")

        post_id = extract_post_id(args.url)
        if not post_id:
            raise URLValidationError(f"Could not extract post ID from URL: {args.url}")
        logger.info(f"Extracted Post ID: {post_id}")

        reddit_client = None # Initialize to None
        try:
            logger.info("Initializing Reddit client...")
            reddit_client = initialize_reddit_client()
            logger.info("Reddit client initialized.")
        except ConfigError as ce:
            # Specific handling for missing config directly during initialization
            logger.error(f"Configuration Error during client initialisation: {ce}", exc_info=True)
            if args.interactive_mode:
                print("\n--- Configuration Required ---", file=sys.stderr)
                print("It looks like the script is not configured correctly.", file=sys.stderr)
                print(f"Error details: {ce}", file=sys.stderr)
                print("Please ensure you have created a `.env` file in the script's directory.", file=sys.stderr)
                print("This file needs to contain your Reddit API credentials:", file=sys.stderr)
                print("  REDDIT_CLIENT_ID=\"YOUR_CLIENT_ID\"", file=sys.stderr)
                print("  REDDIT_USER_AGENT=\"YourAppName/1.0 by /u/YourRedditUsername\"", file=sys.stderr)
                print("For detailed setup instructions, please refer to the 'Setting Up Your Reddit Application' and 'Configure API Credentials' sections in the README.md file.", file=sys.stderr)
                print("----------------------------\n", file=sys.stderr)
                exit_code = 1
                return exit_code # Exit directly after interactive message
            else:
                # In script mode, let the standard error handling catch it
                raise ce 
        except APIAuthenticationError as auth_err:
            # Handle auth errors that might occur during init separately if needed
            # Or let the main handler catch them. For now, re-raise.
             logger.error(f"API Authentication Error during client initialisation: {auth_err}", exc_info=True)
             raise auth_err


        # Fetch the submission object once
        logger.info(f"Fetching submission object for post ID: {post_id}")
        submission = reddit_client.submission(id=post_id)
        # Ensure submission is loaded (PRAW does this lazily)
        # Accessing an attribute like submission.title will trigger the load.
        # Check if submission exists and hasn't been deleted (author is None)
        try:
            # Accessing author triggers fetch; handles deleted posts where author is None
            _ = submission.author 
            # Check if title exists as well, just in case
            if not hasattr(submission, 'title') or submission.title is None:
                 raise PostRetrievalError(f"Failed to load submission details for post ID {post_id}. The post may be deleted, private, or inaccessible.")
        except Exception as sub_error: # Catch prawcore NotFound, etc.
            logger.error(f"Error accessing submission details for {post_id}: {sub_error}", exc_info=True)
            raise PostRetrievalError(f"Failed to load submission details for post ID {post_id}. The post may be deleted, private, or inaccessible.") from sub_error

        logger.info(f"Submission object for '{submission.title}' fetched.")


        logger.info(f"Fetching post data for {post_id}...")
        post_data = fetch_post_data(reddit_client, post_id, include_raw_media_details=args.include_raw_media)
        logger.info(f"Post data fetched for '{post_data.get('title', 'N/A')}'")

        comments_data = []
        if args.comment_limit is None or args.comment_limit > 0: # Fetch if all or N > 0
            logger.info(f"Fetching comments (Num: {args.comment_limit if args.comment_limit is not None else 'all'}, Sort: {args.sort}, Depth: {args.depth if args.depth is not None else 'all'})...")
            comments_data = fetch_comments_data(
                submission=submission, # Pass the submission object
                sort_order=args.sort,
                num_comments=args.comment_limit if args.comment_limit is not None else 1000, # Default to a high number if 'all' was chosen for num_comments
                comment_depth=args.depth
            )
            logger.info(f"Fetched {len(comments_data)} top-level comments.")
        elif args.comment_limit == 0:
            logger.info("Skipping comment fetching as per user request (--no-comments or --comments 0).")

        logger.info("Formatting data as JSON...")
        final_data = format_data_as_json(post_data, comments_data)
        logger.info("Data formatting complete.")

        if args.print:
            logger.info("Printing JSON data to console...")
            try:
                print(json.dumps(final_data, ensure_ascii=False, indent=4))
                logger.info("JSON data printed to console.")
            except Exception as e:
                logger.error(f"Error printing JSON to console: {e}", exc_info=True)
                raise OutputError(f"Failed to print JSON to console: {e}") from e
        else:
            output_filename = args.output if args.output else generate_filename(post_data['id'], post_data['title'])
            if not output_filename.lower().endswith('.json'):
                logger.debug(f"Appending .json to user-provided filename: {output_filename}")
                output_filename += '.json'
            
            logger.info(f"Saving data to file: {output_filename}...")
            save_json_to_file(final_data, output_filename)
            logger.info(f"Data successfully saved to {output_filename}")

            # --- Media Download Logic (Interactive Mode Only, After File Save) ---
            if args.interactive_mode:
                post_media_urls = _get_post_media_urls(post_data)
                comment_media_urls = [] # Initialize
                if args.comment_limit is None or args.comment_limit > 0: # Only try if comments were fetched
                    comment_media_urls = _get_comment_media_urls(comments_data)
                
                total_media_urls_found = len(post_media_urls) + len(comment_media_urls)
                # Refine the condition to prompt for download only if any media is found
                # and to specify where it was found.
                prompt_for_download = False
                if post_media_urls and not comment_media_urls:
                    print("Media detected in the main post.")
                    prompt_for_download = True
                elif not post_media_urls and comment_media_urls:
                    print("Media detected in the comments.")
                    prompt_for_download = True
                elif post_media_urls and comment_media_urls:
                    print("Media detected in both the main post and comments.")
                    prompt_for_download = True

                if prompt_for_download:
                    if prompt_media_download_confirmation(): # This prompt might need slight rephrasing now
                        download_scope = prompt_media_download_scope()
                        
                        urls_to_download = []
                        if download_scope == 'post':
                            urls_to_download.extend(post_media_urls)
                        elif download_scope == 'comments':
                            urls_to_download.extend(comment_media_urls)
                        elif download_scope == 'both':
                            # Combine and ensure uniqueness (though set should handle it in helpers)
                            urls_to_download.extend(post_media_urls)
                            for url in comment_media_urls:
                                if url not in urls_to_download:
                                    urls_to_download.append(url)
                        
                        if urls_to_download:
                            media_folder_name = output_filename.rsplit('.', 1)[0]
                            if not os.path.exists(media_folder_name):
                                try:
                                    os.makedirs(media_folder_name)
                                    logger.info(f"Created media download folder: {media_folder_name}")
                                except OSError as e:
                                    logger.error(f"Could not create media download folder '{media_folder_name}': {e}")
                                    urls_to_download = [] # Prevent download attempts if folder fails
                            
                            if os.path.exists(media_folder_name) and urls_to_download:
                                logger.info(f"Preparing to download {len(urls_to_download)} media item(s) to '{media_folder_name}' based on scope: {download_scope}...")
                                downloaded_count = 0
                                failed_count = 0
                                for index, item_url in enumerate(urls_to_download):
                                    if download_media_item(item_url, media_folder_name, item_index=index):
                                        downloaded_count += 1
                                    else:
                                        failed_count += 1
                                
                                if downloaded_count > 0:
                                    print(f"Successfully downloaded {downloaded_count} media item(s) to '{media_folder_name}'.")
                                if failed_count > 0:
                                    print(f"Failed to download {failed_count} media item(s). Check logs for details.")
                                if downloaded_count == 0 and failed_count == 0 and urls_to_download:
                                    print(f"No media items were downloaded. All {len(urls_to_download)} URLs may have been unsuitable or resulted in errors.")
                            elif not urls_to_download and os.path.exists(media_folder_name):
                                logger.info("Media folder exists but no URLs to download after processing scope or due to folder creation error.")
                            elif not urls_to_download:
                                logger.info("No media URLs to download or folder creation failed.")
                        else:
                            logger.info(f"No media URLs to download based on selected scope: '{download_scope}'.")
                else:
                    logger.info("No media detected in the post or comments, or media is not of a directly downloadable type.")

        logger.info("--- Reddit Content Extractor Finished Successfully ---")

    except RedditExtractorError as e:
        # Only attempt to use args if it was successfully assigned
        is_interactive = args.interactive_mode if args else False 
        user_msg = format_user_error_message(e)
        logger.error(f"A known application error occurred: {user_msg}", exc_info=True)
        # Avoid printing the detailed interactive message again if it was a ConfigError handled above
        if not (is_interactive and isinstance(e, ConfigError)):
             print(f"\nError: {user_msg}\nPlease check the logs for more details if a log file was specified.", file=sys.stderr)
        exit_code = 1 
    except Exception as e: 
        user_msg = format_user_error_message(e)
        logger.critical(f"An unexpected critical error occurred: {user_msg}", exc_info=True)
        print(f"\nAn Critical Unexpected Error Occurred: {user_msg}\nPlease check logs or report this issue.", file=sys.stderr)
        exit_code = 1
    return exit_code

if __name__ == "__main__":
    sys.exit(main()) 