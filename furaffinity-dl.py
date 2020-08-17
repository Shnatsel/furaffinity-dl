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

'''
Please refer to LICENSE for licensing conditions.

current ideas / things to do:
 -r replenish, keep downloading until it finds a already downloaded file
 -n number of posts to download
 metadata injection (gets messy easily)
 sqlite database
 support for classic theme
 turn this into a module
'''

# Argument parsing
parser = argparse.ArgumentParser(formatter_class=RawTextHelpFormatter, description='Downloads the entire gallery/scraps/favorites of a furaffinity user', epilog='''
Examples:
 python3 fadl.py gallery koul
 python3 fadl.py -o koulsArt gallery koul
 python3 fadl.py -o mylasFavs favorites mylafox\n
You can also log in to FurAffinity in a web browser and load cookies to download restricted content:
 python3 fadl.py -c cookies.txt gallery letodoesart\n
DISCLAIMER: It is your own responsibility to check whether batch downloading is allowed by FurAffinity terms of service and to abide by them.
''')
parser.add_argument('category', metavar='category', type=str, nargs='?', default='gallery',
                    help='the category to download, gallery/scraps/favorites')
parser.add_argument('username', metavar='username', type=str, nargs='?',
                    help='username of the furaffinity user')
parser.add_argument('-o', metavar='output', dest='output', type=str, default='.', help="output directory")
parser.add_argument('-c', metavar='cookies', dest='cookies', type=str, default='', help="path to a NetScape cookies file")
parser.add_argument('-u', metavar='useragent', dest='ua', type=str, default='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:68.7) Gecko/20100101 Firefox/68.7', help="Your browser's useragent, may be required, depending on your luck")
parser.add_argument('-s', metavar='start', dest='start', type=str, default=1, help="page number to start from")

args = parser.parse_args()
if args.username is None:
    parser.print_help()
    exit()

# Create output directory if it doesn't exist
if args.output != '.':
    os.makedirs(args.output, exist_ok=True)

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
page_num = args.start

def download_file(url, fname, desc):
    r = session.get(url, stream=True)
    if r.status_code != 200:
        print("Got a HTTP {} while downloading; skipping".format(r.status_code))
        return False
    
    total = int(r.headers.get('Content-Length', 0))
    with open(fname, 'wb') as file, tqdm(
        desc=desc.ljust(40)[:40],
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

    image = s.find(class_='download').find('a').attrs.get('href')
    title = s.find(class_='submission-title').find('p').contents[0]
    filename = image.split("/")[-1:][0]
    data = {
        'id': int(path.split('/')[-2:-1][0]),
        'filename': filename,
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

    # Extact tags
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

    url ='https:{}'.format(image)
    output_path = os.path.join(args.output, filename)
    
    if not download_file(url, output_path, data["title"]):
        return False

    # Write a UTF-8 encoded JSON file for metadata
    with open(os.path.join(args.output, '{}.json'.format(filename)), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# Main downloading loop
while True:
    page_url = '{}/{}'.format(gallery_url, page_num)
    response = session.get(page_url)
    s = BeautifulSoup(response.text, 'html.parser')

    # Account status
    if page_num == 1:
        if s.find(class_='loggedin_user_avatar') is not None:
            account_username = s.find(class_='loggedin_user_avatar').attrs.get('alt')
            print('Logged in as', account_username)
        else:
            print('Not logged in, NSFW content is inaccessible')

    # System messages
    if s.find(class_='notice-message') is not None:
        message = s.find(class_='notice-message').find('div')
        for ele in message:
            if ele.name is not None:
                ele.decompose()

        raise Exception('System Message', message.text.strip())

    # End of gallery
    if s.find(id='no-images') is not None:
        print('End of gallery')
        break

    # Download all images on the page
    for img in s.findAll('figure'):
        download(img.find('a').attrs.get('href'))

    # Favorites galleries use a weird timestamp system, so grab the next "page" from the Next button
    if args.category == 'favorites':
        next_button = s.find('a', class_='button standard right')
        if next_button is None:
            break

        # URL looks something like /favorites/:username/:timestamp/next
        # Splitting on the username is more robust to future URL changes
        page_num = next_button.attrs['href'].split(args.username + '/')[-1]
    else:
        page_num += 1
    
    print('Downloading page', page_num)

print('Finished downloading')
