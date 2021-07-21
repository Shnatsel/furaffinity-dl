#!/usr/bin/python3
import argparse
from tqdm import tqdm
from argparse import RawTextHelpFormatter
import json
from bs4 import BeautifulSoup
import requests
import http.cookiejar as cookielib
import re
import os
from time import sleep
from colorama import init, Fore, Style

init(autoreset=True)

'''
Please refer to LICENSE for licensing conditions.
'''

# Argument parsing
parser = argparse.ArgumentParser(formatter_class=RawTextHelpFormatter, description='Downloads the entire gallery/scraps/favorites of a furaffinity user', epilog='''
Examples:
 python3 furaffinity-dl.py gallery koul
 python3 furaffinity-dl.py -o koulsArt gallery koul
 python3 furaffinity-dl.py -o mylasFavs favorites mylafox\n
You can also log in to FurAffinity in a web browser and load cookies to download restricted content:
 python3 furaffinity-dl.py -c cookies.txt gallery letodoesart\n
DISCLAIMER: It is your own responsibility to check whether batch downloading is allowed by FurAffinity terms of service and to abide by them.
''')
parser.add_argument('category', metavar='category', nargs='?', default='gallery', help='the category to download, gallery/scraps/favorites')
parser.add_argument('username', metavar='username', nargs='?', help='username of the furaffinity user')
parser.add_argument('folder', metavar='folder', nargs='?', help='name of the folder')
parser.add_argument('--output', '-o', dest='output', default='.', help="output directory")
parser.add_argument('--cookies', '-c', dest='cookies', default='', help="path to a NetScape cookies file")
parser.add_argument('--ua', '-u', dest='ua', default='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:68.7) Gecko/20100101 Firefox/68.7', help="Your browser's useragent, may be required, depending on your luck")
parser.add_argument('--start', '-s', dest='start', default=1, help="page number to start from")
parser.add_argument('--dont-redownload', '-d', const='dont_redownload', action='store_const', help="Don't redownload files that have already been downloaded")
parser.add_argument('--interval', '-i', dest='interval', type=float, default=0, help="delay between downloading pages")
parser.add_argument('--metadir', '-m', dest='metadir', default=None, help="directory to put meta files in")
parser.add_argument('--tree', '-t', const='tree', action='store_const', help="split downloads into folders by author")

args = parser.parse_args()
if args.username is None:
    parser.print_help()
    exit()

# Create output directory if it doesn't exist
if args.output != '.':
    os.makedirs(args.output, exist_ok=True)
    
if args.metadir == None:
    args.metadir = args.output
else:
    os.makedirs(args.metadir, exist_ok=True)


# Check validity of category
valid_categories = ['gallery', 'favorites', 'scraps']
if args.category not in valid_categories:
    raise Exception('Category is not valid', args.category)

# Check validity of username
if bool(re.compile(r'[^a-zA-Z0-9\-~._]').search(args.username)):
    raise Exception('Username contains non-valid characters', args.username)

# Initialise a session
session = requests.session()
session.headers.update({'User-Agent': args.ua})

# Load cookies from a netscape cookie file (if provided)
if args.cookies != '':
    cookies = cookielib.MozillaCookieJar(args.cookies)
    cookies.load()
    session.cookies = cookies

base_url = 'https://www.furaffinity.net'
gallery_url = '{}/{}/{}'.format(base_url, args.category, args.username)
if args.folder is not None:
    gallery_url += "/folder/"
    gallery_url += args.folder
page_num = args.start


def download_file(url, fname, desc):
    r = session.get(url, stream=True)
    if r.status_code != 200:
        print(Fore.YELLOW + 'Got a ' + Fore.RED + 'HTTP ' + str(r.status_code) + Fore.YELLOW + ' while downloading; skipping')
        return False

    total = int(r.headers.get('Content-Length', 0))
    with open(fname, 'wb') as file, tqdm(
        desc=desc.ljust(80)[:80],
        total=total,
        miniters=100,
        unit='b',
        unit_scale=True,
        unit_divisor=1024
    ) as bar:
        for data in r.iter_content(chunk_size=1024):
            size = file.write(data)
            bar.update(size)
    return True

# The cursed function that handles downloading
def download(path):
    page_url = '{}{}'.format(base_url, path)
    response = session.get(page_url)
    s = BeautifulSoup(response.text, 'html.parser')

    # System messages
    if s.find(class_='notice-message') is not None:
        message = s.find(class_='notice-message').find('div').find(class_="link-override").text.strip()
        raise Exception('System Message', message)

    image = s.find(class_='download').find('a').attrs.get('href')
    title = s.find(class_='submission-title').find('p').contents[0]
    filename = image.split("/")[-1:][0]
    data = {
        'id': int(path.split('/')[-2:-1][0]),
        'filename': filename,
        'url': page_url,
        'author': s.find(class_='submission-id-sub-container').find('a').find('strong').text,
        'date': s.find(class_='popup_date').attrs.get('title'),
        'title': title,
        'description': s.find(class_='submission-description').text.strip().replace('\r\n', '\n'),
        "tags": [],
        'category': s.find(class_='info').find(class_='category-name').text,
        'type': s.find(class_='info').find(class_='type-name').text,
        'species': s.find(class_='info').findAll('div')[2].find('span').text,
        'gender': s.find(class_='info').findAll('div')[3].find('span').text,
        'views': int(s.find(class_='views').find(class_='font-large').text),
        'favorites': int(s.find(class_='favorites').find(class_='font-large').text),
        'rating': s.find(class_='rating-box').text.strip(),
        'comments': []
    }

    # Extract tags
    for tag in s.find(class_='tags-row').findAll(class_='tags'):
        data['tags'].append(tag.find('a').text)

    # Extract comments
    for comment in s.findAll(class_='comment_container'):
        temp_ele = comment.find(class_='comment-parent')
        parent_cid = None if temp_ele is None else int(temp_ele.attrs.get('href')[5:])

        # Comment is deleted or hidden
        if comment.find(class_='comment-link') is None:
            continue

        data['comments'].append({
            'cid': int(comment.find(class_='comment-link').attrs.get('href')[5:]),
            'parent_cid': parent_cid,
            'content': comment.find(class_='comment_text').contents[0].strip(),
            'username': comment.find(class_='comment_username').text,
            'date': comment.find(class_='popup_date').attrs.get('title')
        })

    url = 'https:{}'.format(image)

    if args.tree:
        output_path = os.path.join(args.output, data["author"].strip('.'))
        metadir_path = os.path.join(args.metadir, data["author"].strip('.'))
    else:
        output_path = os.path.join(args.output)
        metadir_path = os.path.join(args.metadir)

    if not os.path.isdir(output_path):
        print(Fore.GREEN + 'Creating directory for: ' + Fore.CYAN + data["author"])
        os.makedirs(output_path, exist_ok=True)
        os.makedirs(metadir_path, exist_ok=True)

    output_file = os.path.join(output_path, filename)
    descstr = Fore.CYAN + data["author"] + Fore.WHITE + ': ' + Fore.MAGENTA + data["title"]
    # Write a UTF-8 encoded JSON file for metadata
    with open(os.path.join(metadir_path, '{}.json'.format(filename)), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    if not args.dont_redownload or not os.path.isfile(output_file):
        if not download_file(url, output_file, descstr):
            return False
        else:
            sleep(args.interval)
    else:
        print(Fore.YELLOW + 'Skipping: ' + descstr + Fore.YELLOW + ', since it\'s already downloaded')

    return True


# Main downloading loop
while True:
    if page_num == 1:
        page_url = '{}/{}'.format(gallery_url, page_num)
    else:
        page_url = '{}/{}/next'.format(gallery_url, page_num)

    response = session.get(page_url)
    s = BeautifulSoup(response.text, 'html.parser')

    # Account status
    if page_num == 1:
        if s.find(class_='loggedin_user_avatar') is not None:
            account_username = s.find(class_='loggedin_user_avatar').attrs.get('alt')
            print(Fore.GREEN + 'Logged in as ' + Fore.CYAN + account_username)
        else:
            print(Fore.YELLOW + 'Not logged in, NSFW content is inaccessible')

    print(Fore.GREEN + 'Downloading page ' + Fore.CYAN + str(page_num))

    # System messages
    if s.find(class_='notice-message') is not None:
        message = s.find(class_='notice-message').find('div').find(class_="link-override").text.strip()
        raise Exception('System Message', message)

    # End of gallery
    if s.find(id='no-images') is not None:
        print(Fore.GREEN + 'End of gallery')
        break

    # Download all images on the page
    for img in s.findAll('figure'):
        download(img.find('a').attrs.get('href'))

    next_button = s.find('a', class_='button standard right', text="Next")
    if next_button is None:
        print(Fore.YELLOW + 'Unable to find next button')
        break
    page_num = next_button.attrs.get('href').split('/')[-2]

print(Fore.WHITE + 'Finished downloading')
