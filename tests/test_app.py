import os
import unittest
from http import HTTPStatus

import html5lib
import requests

from app import app, success_story_generator

try:
    TEST_HREF = bool(int(os.environ.get('TEST_HREF', 0)))
except ValueError:
    TEST_HREF = False
_HREF_VISITED = set()


def _verify(url):
    for hostname in [
            'legna.com.do',  # wrong certificate
            'www.impulsalicante.es',  # wrong certificate
            ]:
        if hostname in url:
            return False
    return True


def _skip(url):
    for hostname in [
            'aiims.edu',  # random failure
            'www.atida.com',  # block python-requests
            'twitter.com',  # restrict to some browsers
            ]:
        if hostname in url:
            return True
    return False


class TestApp(unittest.TestCase):
    def setUp(self):
        app.testing = True
        app.config['SERVER_NAME'] = 'localhost'
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        self.parser = html5lib.HTMLParser(strict=True)

    def tearDown(self):
        self.app_context.pop()
        self.app_context = None
        self.client = None

    def assertStatic(self, document):
        for el in document.iterfind('.//*[@src]'):
            src = el.attrib['src']
            if src.startswith(app.static_url_path):
                with self.subTest(src=src):
                    response = self.client.get(src)
                    self.assertEqual(response.status_code, HTTPStatus.OK)

    def assertHref(self, document):
        if not TEST_HREF:
            return
        for link in document.iterfind('.//*[@href]'):
            href = link.attrib['href']
            if href.startswith('http'):
                if _skip(href) or href in _HREF_VISITED:
                    continue
                with self.subTest(href=href):
                    verify = _verify(href)
                    headers = {
                        # Some sites forbid python-requests
                        'User-Agent': 'Mozilla/5.0',
                        }
                    response = requests.head(
                        href, verify=verify, allow_redirects=True,
                        headers=headers)
                    if response.status_code in {
                            HTTPStatus.FORBIDDEN,
                            HTTPStatus.METHOD_NOT_ALLOWED,
                            }:
                        response = requests.get(
                            href, verify=verify, headers=headers)
                    response.raise_for_status()
                    _HREF_VISITED.add(href)

    def test_get_routes(self):
        for rule in app.url_map.iter_rules():
            if rule.endpoint == 'flask_sitemap.sitemap':
                continue
            if 'GET' in rule.methods and not rule.arguments:
                with self.subTest(endpoint=rule.endpoint):
                    response = self.client.get(app.url_for(rule.endpoint))

                    if 200 <= response.status_code < 300:
                        if response.mimetype == 'test/html':
                            document = self.parser.parse(response.data)
                            self.assertStatic(document)
                            self.assertHref(document)
                    elif 300 <= response.status_code < 400:
                        self.assertIn('Location', response.headers)
                        pass
                    else:
                        self.fail(f"status code: {response.status_code}")

    def test_success_stories(self):
        for endpoint, arguments in success_story_generator():
            with self.subTest(endpoint=endpoint, arguments=arguments):
                response = self.client.get(app.url_for(endpoint, **arguments))

                self.assertEqual(response.status_code, HTTPStatus.OK)
                self.assertEqual(response.mimetype, 'text/html')
                document = self.parser.parse(response.data)
                self.assertStatic(document)
                self.assertHref(document)

    def test_events(self):
        for event in ['tum2019', 'tsd2019', 'tsd2021']:
            with self.subTest(event=event):
                response = self.client.get(app.url_for('event', event=event))

                self.assertEqual(response.status_code, HTTPStatus.OK)
                self.assertEqual(response.mimetype, 'text/html')
                document = self.parser.parse(response.data)
                self.assertStatic(document)
                self.assertHref(document)

    def test_robots(self):
        response = self.client.get('/robots.txt')

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.mimetype, 'text/plain')
