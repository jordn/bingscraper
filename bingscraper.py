import argparse
import hashlib
import imghdr
import logging
import os
import posixpath
import re
import signal
import socket
import threading
import time
import urllib.parse
import urllib.request

logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# CONFIG
LOG_DIR = './.bingscraper'
DEFAULT_OUTPUT_DIR = './images/'  # default output dir
socket.setdefaulttimeout(2)
_REQUEST_HEADER = {
    'User-Agent': 'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:60.0) '
                  'Gecko/20100101 Firefox/60.0'
}


class DownloadTracker:
    """Keeps track of URLs tried and images downloaded to prevent duplication."""

    def __init__(self, log_dir: str = LOG_DIR):
        self._log_dir = log_dir
        self.tried_urls = set()
        self.image_md5s = dict()
        self.count = 0

    def _get_tried_urls(self):
        try:
            with open(os.path.join(self._log_dir, 'tried_urls.txt'), 'r') as url_file:
                tried_urls = set([line.strip() for line in url_file])
        except FileNotFoundError:
            tried_urls = set()
        return tried_urls

    def _get_image_md5s(self):
        try:
            image_md5s = {}
            with open(os.path.join(self._log_dir, 'image_md5s.tsv'), 'r') as tsv:
                for line in tsv:
                    md5, name = line.strip().split('\t')
                    image_md5s[md5] = name
        except FileNotFoundError:
            image_md5s = {}
        return image_md5s

    @classmethod
    def load(self, log_dir):
        """Log the URLs that have been downloaded."""
        self.tried_urls = self._get_tried_urls()
        self.image_md5s = self._get_image_md5s()

    def log(self):
        """Log the URLs that have been downloaded."""
        with open(os.path.join(self._log_dir, 'tried_urls.txt'), 'w') as url_file:
            url_file.write("\n".join(sorted(self.tried_urls)))
        with open(os.path.join(self._log_dir, 'image_md5s.tsv'), 'w') as image_md5s_tsv:
            for hash, file in self.image_md5s.items():
                image_md5s_tsv.write(f"{hash}\t{file}\n")


def download_image(url: str,
                   dest: str,
                   thread_pool: threading.Semaphore = None,
                   tracker: DownloadTracker = None):
    """Threaded download image of an image URL."""
    if not tracker:
        tracker = DownloadTracker()

    if url in tracker.tried_urls:
        return

    # Get the file name of the image.
    url_path = urllib.parse.urlsplit(url).path
    filename = posixpath.basename(url_path).split('?')[0]
    name, ext = os.path.splitext(filename)

    if thread_pool:
        thread_pool.acquire()

    tracker.tried_urls.add(url)
    try:
        request = urllib.request.Request(url, None, _REQUEST_HEADER)
        image = urllib.request.urlopen(request).read()
        if not imghdr.what(None, image):
            logging.info(f"FAIL: Invalid image {filename} (not saving).")
            return
        md5_hash = hashlib.md5(image).hexdigest()
        if md5_hash in tracker.image_md5s:
            logging.info(f"SKIP: Image {filename} is a duplicate of "
                         f"{image_md5s[md5_hash]} (not saving)")
            return
        tracker.image_md5s[md5_hash] = filename

        saved_filename = md5_hash + ext.lower()
        with open(os.path.join(dest, saved_filename), 'wb') as image_file:
            image_file.write(image)
        logging.info(f"OK: Image {saved_filename} from {filename}")
    except (urllib.error.HTTPError, urllib.error.URLError) as err:
        print(f"FAIL: {filename}, {err.code}")
    finally:
        if thread_pool:
            thread_pool.release()


def query_url(query: str, image_index: int = 0, adult_filter: bool = True,
              filters: str = None):
    """Create the Bing search query."""

    return ("https://www.bing.com/images/async?"
            "q={query}&"
            "first={page}&"
            "count=35&"
            "adlt={adult_filter}&"
            "qft={filters}"
            "".format(query=urllib.parse.quote_plus(query),
                      page=image_index,
                      adult_filter='' if adult_filter else 'off',
                      filters=filters))


def get_image_urls(query: str,
                   filters: str = '',
                   adult_filter: bool = True,
                   image_index: int = 0):
    """Extract image urls from the Bing results page."""
    request_url = query_url(query=query,
                            image_index=image_index,
                            adult_filter=adult_filter,
                            filters=filters)
    logging.info(f'Requesting {request_url}')
    request = urllib.request.Request(request_url, headers=_REQUEST_HEADER)
    response = urllib.request.urlopen(request)
    html = response.read().decode('utf8')
    uris = re.findall('murl&quot;:&quot;(.*?)&quot;', html)
    return uris


def fetch_images(query: str,
                 output_dir: str,
                 limit: int = 50,
                 filters: str = '',
                 adult_filter: bool = True,
                 threads: int = 20):
    """Fetch images and place the output in output_dir."""
    thread_pool = threading.BoundedSemaphore(threads)
    image_index = 0
    tracker = DownloadTracker()

    def interupt_handler(*args):
        tracker.log()
        if args:
            exit(0)

    signal.signal(signal.SIGINT, interupt_handler)

    dest = os.path.join(output_dir, query.replace(' ', '_'))
    os.makedirs(dest, exist_ok=True)

    while image_index < limit:
        image_urls = get_image_urls(
            query=query, filters=filters, adult_filter=adult_filter,
            image_index=image_index)
        for i, url in enumerate(image_urls):
            t = threading.Thread(
                target=download_image,
                kwargs=dict(
                    thread_pool=thread_pool,
                    url=url,
                    dest=dest,
                    tracker=tracker))
            t.start()
        image_index += i
        time.sleep(0.1)
    tracker.log()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Bulk image downloader')
    parser.add_argument("-q", "--query", required=True,
                        help="Search query for Bing Image API.")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help="Path to output directory of images")
    parser.add_argument('--disable-adult-filter',
                        help='Disable the adult content filter.',
                        action='store_true',
                        required=False)
    parser.add_argument('--filters',
                        help='Any query based filters you want to append when '
                             'searching for images, e.g. +filterui:license-L1',
                        required=False)
    parser.add_argument('--limit',
                        help='Max number of images.',
                        type=int,
                        default=100)
    parser.add_argument('--threads',
                        help='Number of threads',
                        type=int,
                        default=20)
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    fetch_images(query=args.query,
                 output_dir=args.output_dir,
                 limit=args.limit,
                 filters=args.filters,
                 adult_filter=not args.disable_adult_filter)
