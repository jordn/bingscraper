# bingscraper

Bulk image downloader scraped from Bing Image Search


## Usage

```
$ python3 bingscraper.py --help
usage: bingscraper.py [-h] -q QUERY [-o OUTPUT_DIR] [--disable-adult-filter]
                      [--filters FILTERS] [--limit LIMIT] [--threads THREADS]

Bulk image downloader

optional arguments:
  -h, --help            show this help message and exit
  -q QUERY, --query QUERY
                        Search query for Bing Image API.
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
                        Path to output directory of images
  --disable-adult-filter
                        Disable the adult content filter.
  --filters FILTERS     Any query based filters you want to append when
                        searching for images, e.g. +filterui:license-L1
  --limit LIMIT         Max number of images.
  --threads THREADS     Number of threads
```

## Example

```
python3 bingscraper.py -q puppy -l 500
```

Will download 500 images of puppies (hopefully) to the folder `images/puppy`