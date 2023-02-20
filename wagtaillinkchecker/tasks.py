from celery import shared_task
from wagtaillinkchecker.scanner import get_url, clean_url
from wagtaillinkchecker.models import ScanLink
from bs4 import BeautifulSoup
from django.utils.translation import gettext_lazy as _

from django.db.utils import IntegrityError
from django.utils import timezone

from urllib.parse import urlparse


@shared_task
def check_link(link_pk, run_sync=False, verbosity=1):
    link = ScanLink.objects.get(pk=link_pk)
    site = link.scan.site
    url = get_url(link.url, link.page, site)
    link.status_code = url.get('status_code')

    parsed_uri = urlparse(link.page.full_url)
    page_url_root = '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)
    parsed_uri = urlparse(link.url)
    link_url_root = '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)

    if url['error']:
        link.broken = True
        link.error_text = url['error_message']

    elif url['invalid_schema']:
        link.invalid = True
        link.error_text = _('Link was invalid')

    # Check that base URL is actualy our page, otherwise it would scan pages that are not ours
    # This also helps with internationalization compatibility
    elif page_url_root == link_url_root:
        soup = BeautifulSoup(url['response'].content, 'html5lib')
        anchors = soup.find_all('a')
        images = soup.find_all('img')

        for anchor in anchors:
            link_href = anchor.get('href')
            link_href = clean_url(link_href, site)
            if verbosity > 1:
                print(f"cleaned link_href: {link_href}")
            if link_href:
                try:
                    new_link = link.scan.add_link(page=link.page, url=link_href)
                    new_link.check_link(run_sync, verbosity)
                except IntegrityError:
                    pass

        for image in images:
            image_src = image.get('src')
            image_src = clean_url(image_src, site)
            if verbosity > 1:
                print(f"cleaned image_src: {image_src}")
            if image_src:
                try:
                    new_link = link.scan.add_link(page=link.page, url=image_src)
                    new_link.check_link(run_sync, verbosity)
                except IntegrityError:
                    pass
    link.crawled = True
    link.save()

    if link.scan.links.non_scanned_links():
        pass
    else:
        scan = link.scan
        scan.scan_finished = timezone.now()
        scan.save()
