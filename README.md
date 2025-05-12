# Reddit Content Extractor

This Python script extracts the main post content and associated comments from a Reddit submission URL and saves the structured data as a JSON file.

It supports both command-line operation for scripting and an interactive mode for ease of use.

## Table of Contents

- [Reddit Content Extractor](#reddit-content-extractor)
  - [Table of Contents](#table-of-contents)
  - [Features](#features)
  - [Setup](#setup)
  - [Usage](#usage)
    - [Command-Line Mode](#command-line-mode)
    - [Interactive Mode](#interactive-mode)
  - [Output Format](#output-format)
  - [Media Download Feature](#media-download-feature)
  - [Technical Notes on Data Retrieval](#technical-notes-on-data-retrieval)
  - [Troubleshooting](#troubleshooting)
  - [License](#license)

## Features

- Extracts post details (title, author, score, selftext, media info, etc.).
- Extracts comments and their replies up to a specified depth or all replies.
- Supports limiting the number of top-level comments fetched.
- Supports various comment sorting orders (best, top, new, etc.).
- Handles different types of media associated with posts (images, videos, galleries, embeds).
- Provides output in a structured JSON format, including metadata.
- Command-line interface for automation.
- Interactive mode for guided input.
- Robust error handling and retry mechanism for API calls.
- Configurable logging (console and file).

## Setup

1. **Clone the Repository:**

    ```bash
    git clone https://github.com/Captain-Bacon/Reddit_Getter.git
    cd Reddit_Getter # Or your cloned directory name
    ```

2. **Environment Setup:**
    - **Using Conda (Recommended):**

        ```bash
        # Create a new Conda environment (e.g., named 'reddit_extractor')
        conda create -n reddit_extractor python=3.10 # Or desired Python version
        conda activate reddit_extractor
        
        # Install dependencies
        pip install -r requirements.txt
        ```

    - **Using venv:**

        ```bash
        python3 -m venv venv
        source venv/bin/activate # On Windows use `venv\\Scripts\\activate`
        pip install -r requirements.txt
        ```

3. **Setting Up Your Reddit Application:**
    To use this script, you need to register a "script" type application on Reddit. This will provide you with the necessary API credentials.

    - Go to your Reddit App Preferences: [https://www.reddit.com/prefs/apps/](https://www.reddit.com/prefs/apps/)
    - Scroll down to the bottom and click "are you a developer? create an app..."
        - *(Image placeholder: Screenshot of the "create an app" button)*
    - Fill out the form:
        - **Name:** Give your app a descriptive name (e.g., "MyRedditContentExtractor").
        - **Type:** Select the "**installed app**" radio button.
            - *(Image placeholder: Screenshot highlighting the "installed app" option)*
        - **Description:** (Optional) You can leave this blank or add a short description.
        - **About URL:** (Optional) You can leave this blank or link to this GitHub repository.
        - **Redirect URI:** This is important! Enter `http://localhost:8080`. This exact URI is used by the script to receive the authorization code from Reddit.
    - Click the "create app" button.
    - After creation, your app will be listed. Under its name, you will see a string of characters – this is your **Client ID**. A "secret" may also be displayed, but **this script does not use the client secret.**
        - *(Image placeholder: Screenshot of an app entry showing where the Client ID is located)*
    - Make a note of your **Client ID**. You'll need it for the next step.
    - **Note on Logging In:** When the script directs you to Reddit to authorize the app, you can log in using your standard Reddit username and password, or by using Google/Apple sign-in if your Reddit account is linked to them.

4. **Configure API Credentials (`.env` file):**
    - In the project root directory, create a file named `.env`.
    - Copy the contents from `env.example` into your new `.env` file.
    - Fill in the following values:

        ```dotenv
        # .env file content (example)
        REDDIT_CLIENT_ID="YOUR_CLIENT_ID_FROM_REDDIT_APP_SETTINGS"
        REDDIT_USER_AGENT="YourAppName/1.0 by /u/YourRedditUsername" # Be specific and unique!
        REDDIT_REFRESH_TOKEN=""
        ```

    - **`REDDIT_CLIENT_ID`**: Paste the Client ID you obtained from your Reddit app settings in the previous step.
    - **`REDDIT_USER_AGENT`**: Create a unique and descriptive User-Agent string. Reddit requires this for API access, and it helps them identify your script. A good format is `<AppName>/<Version> by /u/<YourRedditUsername>` (e.g., `MyRedditExtractor/0.1 by /u/MyRedditUsername`). **Replace `/u/YourRedditUsername` with your actual Reddit username.** Using a generic or non-unique User-Agent can lead to your script being rate-limited or blocked.
    - **`REDDIT_REFRESH_TOKEN`**: Leave this blank initially. The first time you run the script (e.g., `python reddit_extractor.py`) without a `REDDIT_REFRESH_TOKEN` already set in your `.env` file, the script will guide you through a one-time authorization process to obtain one:
        1. The script will display an authorization URL in your console. Copy this URL and open it in your web browser.
        2. You will be taken to Reddit. Log in if prompted (you can use your standard Reddit credentials or linked Google/Apple accounts) and then explicitly authorize the application's requested permissions.
        3. After successful authorization, Reddit will attempt to redirect your browser to a URL starting with `http://localhost:8080/...`.
        4. **Important Clarification:** Your browser will likely display a "page not found," "connection refused," "this site can't be reached," or a similar error message for this `http://localhost:8080` address. **This is normal and expected.** The script doesn't run a web server; the redirect is simply a mechanism for Reddit to pass back an authorization `code` to you via the URL.
        5. The crucial information is now in your browser's **address bar**. The URL will look something like this:
            `http://localhost:8080/?state=SOME_RANDOM_STRING&code=VERY_LONG_AUTHORIZATION_CODE_STRING#_`
            *(The `state` might be different, and the `code` will be a long string of characters and numbers.)*
        6. You need to **copy the value of the `code` parameter** from this address bar URL. This is the entire string of characters that appears immediately after `code=` and before any subsequent `&` or `#` characters.
        7. The script, in your console, will be prompting you to: `Enter the 'code' from the redirect URL:`. Paste the `code` you just copied from your browser's address bar here and press Enter.
        8. If the `code` is valid, the script will use it to obtain a **Refresh Token** from Reddit. This **Refresh Token** will then be printed clearly in your console.
        9. Copy this entire **Refresh Token** value.
        10. Open your `.env` file and paste this token as the value for `REDDIT_REFRESH_TOKEN`. For example:
            `REDDIT_REFRESH_TOKEN="actual_long_refresh_token_string_here"`
        11. Save your `.env` file. Now, on subsequent runs, the script will use this refresh token to authenticate non-interactively.

## Usage

The script can be run via the command line or interactively.

### Command-Line Mode

Provide the Reddit post URL using the `--url` argument. Other options control comment retrieval and output.

```bash
python reddit_extractor.py --url <reddit_post_url> [options]
```

**Common Options:**

- `--url <URL>`: (Required) The full URL of the Reddit post.
- `--comments <N>`: Get the top `N` comments. Use `0` for no comments.
- `--all-comments`: Get all top-level comments (default if no comment option specified).
- `--no-comments`: Do not fetch any comments.
- `--sort <order>`: Comment sort order (`best`, `top`, `new`, `controversial`, `old`, `q&a`). Default: `best`.
- `--depth <D>`: Maximum reply depth to fetch. Default: all depths. Note: Depth is zero-indexed; `--depth 0` fetches top-level comments only (no replies), `--depth 1` fetches top-level comments and their direct replies, etc.
- `--output <filename.json>` or `-o <filename.json>`: Specify the output JSON filename. If omitted, a name is generated based on post ID and title.
- `--print`: Print the final JSON to the console instead of saving to a file.
- `--verbose` or `-v`: Enable detailed DEBUG level logging to the console.
- `--log-file <filepath>`: Save logs to the specified file (appends).
- `--include-raw-media`: Include extensive raw media metadata from PRAW (e.g., all image resolutions, full gallery data). This can significantly increase file size. Off by default.

**Examples:**

1. **Fetch post and all comments, save to auto-generated file:**

    ```bash
    python reddit_extractor.py --url https://www.reddit.com/r/some_subreddit/comments/post_id/post_title/
    ```

2. **Fetch post and top 50 comments (sorted by new), save to `output.json`:**

    ```bash
    python reddit_extractor.py --url <URL> --comments 50 --sort new -o output.json
    ```

3. **Fetch post only (no comments), print JSON to console:**

    ```bash
    python reddit_extractor.py --url <URL> --no-comments --print
    ```

4. **Fetch all comments up to depth 2, enable verbose logging:**

    ```bash
    python reddit_extractor.py --url <URL> --all-comments --depth 2 -v 
    ```

### Interactive Mode

If you run the script without any arguments (or only logging arguments like `-v`), it will enter interactive mode:

```bash
python reddit_extractor.py
```

The script will prompt you for:

- The Reddit post URL.
- Comment fetching preference (Number, `all`, or `no`).
- Comment sort order (if fetching comments).
- Comment depth limit (if fetching comments). Remember, depth is zero-indexed (0 = top-level only).
- Output filename (optional, leave blank to auto-generate).
- Whether to print output to the console instead of saving.
- Whether to include verbose raw media details (can greatly increase JSON size).
- **Media Download Prompts (if applicable):** After the above steps, if downloadable media is detected in the post or comments, you will be asked if you want to download it and from where (post only, comments only, or both). See the [Media Download Feature](#media-download-feature) section for details.

## Output Format

The script outputs a JSON file containing structured information about the post and its comments. Here's a simplified example illustrating the key fields:

```json
{
  // --- Metadata ---
  "extractor_version": "0.1.0",           // Version of the script used
  "extraction_timestamp_utc": "2025-05-12T10:59:23.026915+00:00", // ISO 8601 timestamp of extraction
  "source_url": "https://www.reddit.com/r/aviation/comments/pcy6v7/...", // Permalink to the original Reddit post

  // --- Post Details ---
  "post_details": {
    "id": "pcy6v7",                         // Reddit's unique post ID
    "title": "What is your favourite fact about the legendary Lockheed SR-71...", // Post title
    "author": "Mean-Juggernaut1560",        // Author's Reddit username
    "created_utc": 1630105229.0,            // Unix epoch timestamp of post creation
    "url": "https://i.redd.it/1j7mmhv8ezj71.jpg", // Direct URL (often to media, or self-post URL)
    "permalink": "https://www.reddit.com/r/aviation/comments/pcy6v7/...", // Full permalink again
    "domain": "i.redd.it",                   // Domain of the main URL (e.g., i.redd.it, self.subreddit, v.redd.it)
    "selftext": "",                         // Body text of the post (empty if it's a link/media post)
    "score": 4736,                          // Net score (upvotes - downvotes)
    "upvote_ratio": 0.95,                   // Ratio of upvotes to total votes
    "num_comments": 770,                    // Number of comments reported by Reddit at time of fetch
    "is_original_content": false,           // Boolean flag
    "is_self": false,                       // True if it's a text-only post (self-post)
    "is_video": false,                      // True if Reddit identifies the main link as a video
    "over_18": false,                       // NSFW flag
    "spoiler": false,                       // Spoiler flag
    "locked": false,                        // Locked post flag
    "subreddit": "aviation",                // Subreddit name
    "subreddit_id": "t5_2qhu8",             // Subreddit's unique ID
    "gilded": 1,                            // Number of times gilded (Reddit Gold/Awards)

    // -- Media Information (list, as some posts have multiple items e.g., galleries) --
    "media_info": [
      {
        "type": "image",                    // Type identifier (image, reddit_video, youtube_video_embed, etc.)
        "url": "https://i.redd.it/1j7mmhv8ezj71.jpg", // Primary URL for the media
        "width": 1242,                      // Media width (if available)
        "height": 1291                      // Media height (if available)
        // Other type-specific fields might appear here (e.g., fallback_url, hls_url for videos)
      }
    ],
    "created_iso": "2021-08-27T23:00:29+00:00" // ISO 8601 formatted creation timestamp
  },

  // --- Comments Section (List of top-level comments) ---
  "comments": [
    { // --- Top-Level Comment Object ---
      "id": "hamg6gr",                      // Comment's unique ID
      "author": "Spiffytown",               // Comment author's username
      "body": "Turning radius: About 5 states", // The comment text
      "created_utc": 1630109018.0,          // Unix epoch timestamp of comment creation
      "score": 1235,                        // Comment's net score
      "is_submitter": false,                // True if comment author is the post author
      "stickied": false,                    // True if comment is stickied by mods
      "parent_id": "t3_pcy6v7",             // ID of the parent (t3_ prefix = post, t1_ prefix = another comment)
      "permalink": "https://www.reddit.com/r/aviation/comments/pcy6v7/.../hamg6gr/", // Full permalink to comment
      "depth": 0,                           // Depth level (0 = top-level reply to post)
      "created_iso": "2021-08-28T00:03:38+00:00", // ISO 8601 formatted creation timestamp

      // -- Replies to this comment (nested list, recursive structure) --
      "replies": [
        { // --- Reply Comment Object (Depth 1) ---
          "id": "hamq4ae",
          "author": "Mean-Juggernaut1560",
          "body": "Turning radius: France",
          "created_utc": 1630113950.0,
          "score": 596,
          "is_submitter": true,            // This comment IS by the post's original submitter
          "stickied": false,
          "parent_id": "t1_hamg6gr",        // Parent is the comment above (t1_ prefix)
          "permalink": "https://www.reddit.com/r/aviation/comments/pcy6v7/.../hamq4ae/",
          "depth": 1,                      // Depth level 1
          "created_iso": "2021-08-28T01:25:50+00:00",
          "replies": [
            // Further nested replies would appear here...
            // If --depth limit was reached, this list would be empty []
          ]
        },
        // ... other replies to the top-level comment ...
      ]
    },
    // ... other top-level comments ...
  ]
}
```

Key points about the structure:

- **Timestamps:** `created_utc` provides the raw Unix epoch time, while `created_iso` offers a human-readable ISO 8601 format.
- **Media:** `post_details.media_info` is a list containing objects for each detected media item (images, videos, embeds). The `type` field helps identify the kind of media. If the `--include-raw-media` flag is used, additional fields prefixed with `_raw_` containing extensive PRAW metadata will appear within `post_details`.
- **Comments:** The `comments` list contains top-level comment objects. Each comment object has a `replies` field which is itself a list containing replies to *that* comment, creating a nested structure. The `depth` field indicates the nesting level (0 for direct replies to the post).

## Media Download Feature

This script can optionally download media (images, GIFs, and some videos) from the main post and/or comments **when running in interactive mode.**

**How it works:**

- After the main data extraction is complete and the JSON output is ready (either printed or saved), the script checks for potential media URLs.
- For the **main post**, it looks at the structured `media_info` within the `post_details` section of the JSON, extracting URLs for types like `image` and `reddit_video` (if they point directly to downloadable files like `.jpg`, `.png`, `.gif`, `.mp4`).
- For **comments**, it scans the `body` text of each fetched comment (and its replies) for direct links to Reddit's media hosting domains (`i.redd.it`, `preview.redd.it`) that end in common image extensions (`.jpg`, `.jpeg`, `.png`, `.gif`).
- If any potential media URLs are found, you will be prompted to confirm if you want to download them and specify the scope (post, comments, or both).
- Downloaded media files are saved into a **new folder** created in the same directory as the output JSON file. This folder will have the **same name as the JSON file (without the `.json` extension)**. For example, if the output is saved as `my_post_output.json`, media will be saved in a folder called `my_post_output/`.

**Limitations for Reddit Videos:**

- Reddit-hosted videos downloaded by this script will **not have sound**. This is because Reddit stores video and audio as separate files/streams, and this script currently only downloads the primary video stream (typically the `.mp4` file found in the media info).
- Images and GIFs are downloaded as expected.

## Technical Notes on Data Retrieval

This script utilises the [PRAW (Python Reddit API Wrapper)](https://praw.readthedocs.io/en/stable/) library to interact with the official Reddit API. Understanding a little about how PRAW fetches data, particularly comments, can be helpful:

- **Comment Limits (`--comments N`):** When you specify a limit for top-level comments, the script first sets `submission.comment_limit` in PRAW. This provides an initial hint to PRAW for its first API request for comments. However, to ensure all potential comments are considered (especially those hidden behind "load more comments" placeholders), the script then calls `submission.comments.replace_more(limit=None)`. This PRAW method makes further API calls if necessary to expand those placeholders and retrieve more comments. Finally, the script iterates through the fetched top-level comments and stops once your specified limit (`N`) is reached. So, it's a combination of PRAW's fetching capabilities and the script's own iteration and counting to meet your exact requirement.

- **Comment Depth (`--depth D`):** Control over comment reply depth is primarily handled by this script after PRAW fetches the comment data. When PRAW retrieves comments (and their replies via `replace_more()`), the Reddit API usually sends replies down to a certain default nesting level. PRAW does not offer a direct way to tell the API "only send replies N levels deep." Instead, this script recursively processes the comment tree provided by PRAW. If a reply's current depth in the tree (where 0 is a direct reply to the post, 1 is a reply to that, etc.) meets or exceeds your specified `--depth D`, the script includes that comment but provides an empty list for its `replies`. For example, `--depth 0` will give you only the top-level comments, and their `replies` field will be `[]`. `--depth 1` will give top-level comments, and their direct replies (depth 1 comments) will be included with their `replies` field set to `[]`.

- **PRAW's Role:** In essence, PRAW handles the complexities of direct API communication, authentication, and provides convenient Python objects representing Reddit posts, comments, etc. This script then intelligently uses these PRAW objects, directs PRAW to fetch further data where needed (like expanding comments), and then processes, filters, and structures this information into the final JSON output according to your specified options.

For more in-depth information on PRAW itself, please refer to the [official PRAW documentation](https://praw.readthedocs.io/en/stable/).

## Troubleshooting

- **Authentication Errors (`APIAuthenticationError`)**:
  - Double-check your `REDDIT_CLIENT_ID` and `REDDIT_USER_AGENT` in your `.env` file.
  - Ensure the `REDDIT_USER_AGENT` is unique and includes your Reddit username.
  - If you have a `REDDIT_REFRESH_TOKEN` in your `.env` file, it might be invalid or expired. Try removing it (leave it blank) and re-running the script to go through the authorization process again and get a new refresh token.
  - Confirm that the `REDIRECT_URI` in your Reddit app settings is exactly `http://localhost:8080`.
- **Post Not Found (`PostRetrievalError`)**: Verify the Reddit URL is correct and the post hasn't been deleted or made private.
- **Rate Limits**: If you encounter errors mentioning rate limits, wait a while before trying again. The script has a basic retry mechanism, but excessive requests can still be blocked.
- **Dependencies Not Found (`ModuleNotFoundError`)**: Ensure you have activated the correct Conda environment or virtual environment (`source venv/bin/activate` or `conda activate <env_name>`) before running `pip install -r requirements.txt` and before running the script.
- **File Saving Issues (`OutputError`)**: Check that you have write permissions in the directory where the script is trying to save the output file.

For more detailed diagnostics, run the script with the `--verbose` flag and check the console output, or use `--log-file <filepath>` to save logs to a file.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.
