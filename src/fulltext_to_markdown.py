#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from getpass import getpass
from argparse import ArgumentParser
from loguru import logger
from pathvalidate import sanitize_filename

from syslira_tools import ZoteroClient, OpenAlexClient, PaperLibrary


def validate_args(args):
    """Validate and sanitize command line arguments."""
    # Validate library type
    if args.zotero_library_type not in ["user", "group"]:
        logger.error(f"Invalid library type: {args.zotero_library_type}. Must be 'user' or 'group'.")
        sys.exit(1)

    # Validate obsidian directory if provided
    if args.obsidian_directory:
        obsidian_path = Path(args.obsidian_directory)
        if not obsidian_path.exists():
            try:
                obsidian_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created directory: {args.obsidian_directory}")
            except OSError as e:
                logger.error(f"Cannot create directory {args.obsidian_directory}: {e}")
                sys.exit(1)
        elif not obsidian_path.is_dir():
            logger.error(f"{args.obsidian_directory} exists but is not a directory")
            sys.exit(1)


def get_interactive_input(args):
    """Get missing required arguments interactively."""
    if not args.zotero_api_key:
        args.zotero_api_key = getpass("Please enter your Zotero API key: ")
        if not args.zotero_api_key.strip():
            logger.error("Zotero API key is required")
            sys.exit(1)

    if not args.zotero_library_id:
        args.zotero_library_id = input("Please enter your Zotero library ID: ").strip()
        if not args.zotero_library_id:
            logger.error("Zotero library ID is required")
            sys.exit(1)

    if not args.zotero_collection_key:
        args.zotero_collection_key = input("Please enter your Zotero collection key: ").strip()
        if not args.zotero_collection_key:
            logger.error("Zotero collection key is required")
            sys.exit(1)

    if not args.obsidian_directory:
        obsidian_input = input("Please enter your Obsidian directory to save markdown files (optional, press Enter to skip): ").strip()
        args.obsidian_directory = obsidian_input if obsidian_input else None


def process_papers(paper_library, obsidian_directory):
    """Process papers and save to markdown files."""
    try:
        result = paper_library.sync_zotero_collection()
        logger.info(result)

        paper_library_df = paper_library.get_library_df()
        if paper_library_df.empty:
            logger.warning("No papers found in the library.")
            return

        logger.info(f"Found {len(paper_library_df)} papers in the library.")

        processed_count = 0
        for paper_index, paper in paper_library_df.iterrows():
            if 'fulltext' in paper and isinstance(paper['fulltext'], str) and paper['fulltext'].strip():
                fulltext = paper['fulltext']
                markdown_text = f"# {paper['title']}\n\n{fulltext}"

                if obsidian_directory:
                    try:
                        paper_title_sanitized = sanitize_filename(paper['title'])
                        file_path = Path(obsidian_directory) / f"{paper_title_sanitized}.md"

                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(markdown_text)

                        logger.info(f"Saved fulltext of paper '{paper['title']}' to {file_path}")
                        processed_count += 1
                    except OSError as e:
                        logger.error(f"Failed to save paper '{paper['title']}': {e}")
                else:
                    logger.info(f"Would process paper '{paper['title']}' (no output directory specified)")
                    processed_count += 1
            else:
                logger.warning(f"No fulltext found for paper '{paper.get('title', f'#{paper_index}')}'")

        logger.info(f"Successfully processed {processed_count} papers")

    except Exception as e:
        logger.error(f"Error processing papers: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = ArgumentParser(
        description="Retrieve fulltext from Zotero, convert to markdown, and add to Obsidian directory",
        epilog="Environment variables: ZOTERO_API_KEY, ZOTERO_LIBRARY_ID, ZOTERO_COLLECTION_KEY, ZOTERO_LIBRARY_TYPE, OBSIDIAN_DIRECTORY"
    )

    parser.add_argument("--zotero-api-key", type=str,
                        default=os.environ.get("ZOTERO_API_KEY"),
                        help="Zotero API key")
    parser.add_argument("--zotero-library-id", type=str,
                        default=os.environ.get("ZOTERO_LIBRARY_ID"),
                        help="Zotero library ID")
    parser.add_argument("--zotero-collection-key", type=str,
                        default=os.environ.get("ZOTERO_COLLECTION_KEY"),
                        help="Zotero collection key")
    parser.add_argument("--zotero-library-type", type=str,
                        default=os.environ.get("ZOTERO_LIBRARY_TYPE", "user"),
                        choices=["user", "group"],
                        help="Zotero library type")
    parser.add_argument("--obsidian-directory", type=str,
                        default=os.environ.get("OBSIDIAN_DIRECTORY"),
                        help="Obsidian directory to save markdown files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be processed without saving files")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging")

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logger.add(sys.stderr, level="DEBUG")

    # Validate arguments
    validate_args(args)

    # Get missing arguments interactively
    get_interactive_input(args)

    try:
        # Initialize clients
        logger.info("Initializing Zotero client...")
        zotero_client = ZoteroClient(args.zotero_api_key, args.zotero_library_id,
                                     library_type=args.zotero_library_type)
        zotero_client.init()

        logger.info("Initializing OpenAlex client...")
        openalex_client = OpenAlexClient()
        openalex_client.init()

        # Set up paper library
        paper_library = PaperLibrary(
            zotero_client=zotero_client,
            openalex_client=openalex_client,
            collection_key=args.zotero_collection_key,
        )

        # Process papers
        obsidian_dir = None if args.dry_run else args.obsidian_directory
        process_papers(paper_library, obsidian_dir)

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()