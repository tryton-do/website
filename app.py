#!/usr/bin/env python3
import ast
import datetime
import functools
import glob
import hashlib
import logging
import os
import re
import unicodedata

from collections import OrderedDict, namedtuple
from functools import partial
from http import HTTPStatus
from logging.handlers import SMTPHandler
from random import sample, shuffle
from operator import attrgetter
from urllib.parse import urlparse

import requests
from colorthief import ColorThief
from flask import (Flask, render_template, redirect, url_for, request,
    make_response, abort)
from flask.logging import default_handler
from flask_caching import Cache
from flask_cdn import CDN, url_for as _cdn_url_for
from flask_gravatar import Gravatar
from flask_sitemap import Sitemap
from icalendar import Calendar
from jinja2 import TemplateNotFound
from lxml import objectify, html
from werkzeug.middleware.proxy_fix import ProxyFix

NEWS_URL = 'https://discuss.tryton.org/c/news'
NEWS_RSS_URL = NEWS_URL + '.rss'
CALENDAR_URL = (
    'https://calendar.google.com/calendar/embed'
    '?src=p4jhgp9j5a2ehndebdglo6tslg%40group.calendar.google.com'
    '&ctz=Europe%2FBrussels')
CALENDAR_ICS = (
    'https://calendar.google.com/calendar/ical'
    '/p4jhgp9j5a2ehndebdglo6tslg%40group.calendar.google.com/public/basic.ics')
SUPPORTERS_URL = (
    'https://foundation.tryton.org:9000/foundation/foundation/1/supporters')
DONATORS_URL = (
    'https://foundation.tryton.org:9000/foundation/foundation/1/donators'
    '?account=732&account=734&duration=730')
DONATIONS_URL = (
    'https://foundation.tryton.org:9000/foundation/foundation/1/donations'
    '?account=732&account=734')

PROVIDERS = [
    ('Adiczion', [(43.52153, 5.43150)]),
    ('B2CK', [(50.631123, 5.567552)]),
    ('Coopengo', [(48.873278, 2.324776)]),
    ('Datalife', [(37.9596885, -1.2086241)]),
    ('First Telecom', [(38.0131591, 23.7721521), (44.83722, 20.40560)]),
    ('gcoop', [(-34.59675, -58.43035)]),
    ('IntegraPer', [(-11.9753824, -77.0860785)]),
    ('INROWGA', [(18.476389, -69.893333)]),
    ('Kopen Software', [(41.5995983, 0.5799085)]),
    ('Lava Lab Software', [(-27.978905, 153.389466)]),
    ('m-ds', [(52.520008, 13.404954)]),
    ('NaN-tic', [(41.544063, 2.115122)]),
    ('power solutions', [(47.0467674, 8.3048232)]),
    ('SISalp', [(45.903956, 6.099937), (43.132028, 5.935532)]),
    ('Virtual Things', [(48.13585, 11.577415), (50.775116, 6.083565)]),
    ]

cache = Cache(config={'CACHE_TYPE': 'simple'})
if os.environ.get('MEMCACHED'):
    cache.config['CACHE_TYPE'] = 'memcached'
    cache.config['CACHE_MEMCACHED_SERVERS'] = (
        os.environ['MEMCACHED'].split(','))
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = datetime.timedelta(days=365)
app.config['CACHE_DEFAULT_TIMEOUT'] = 60 * 60
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['SERVER_NAME'] = os.environ.get('SERVER_NAME')
app.config['SITEMAP_INCLUDE_RULES_WITHOUT_PARAMS'] = True
app.config['SITEMAP_VIEW_DECORATORS'] = [cache.cached()]
app.config['SITEMAP_IGNORE_ENDPOINTS'] = [
    'news-alt', 'news_rss', 'event-alt', 'success_stories-alt', 'download-alt',
    'presentations-alt', 'contribute-alt', 'foundation-alt', 'supporters-alt',
    'donate-alt', 'donate_thanks', 'donate_cancel', 'service_providers-alt',
    'sitemap.xml']
app.config['CDN_DOMAIN'] = os.environ.get('CDN_DOMAIN')
app.config['CDN_HTTPS'] = ast.literal_eval(os.environ.get('CDN_HTTPS', 'True'))
app.config['SITEMAP_IGNORE_ENDPOINTS'] = ['events', 'events-alt']
app.config['GRAVATAR_SIZE'] = 198
app.config['GRAVATAR_DEFAULT'] = 'mp'
app.config['GRAVATAR_USE_SSL'] = True
if app.config['CDN_DOMAIN']:
    app.config['GRAVATAR_BASE_URL'] = '%s://%s/' % (
        'https' if app.config['CDN_HTTPS'] else 'http',
        app.config['CDN_DOMAIN'])
else:
    app.config['GRAVATAR_BASE_URL'] = '/'
app.jinja_env.lstrip_blocks = True
app.jinja_env.trim_blocks = True
cache.init_app(app)
CDN(app)
gravatar = Gravatar(app)
sitemap = Sitemap(app=app)

_slugify_strip_re = re.compile(r'[^\w\s-]')
_slugify_hyphenate_re = re.compile(r'[-\s]+')


@app.template_filter('slugify')
def slugify(value):
    if not isinstance(value, str):
        value = str(value)
    value = unicodedata.normalize('NFKD', value)
    value = str(_slugify_strip_re.sub('', value).strip())
    return _slugify_hyphenate_re.sub('-', value)


def cdn_url_for(*args, **kwargs):
    if app.config['CDN_DOMAIN']:
        return _cdn_url_for(*args, **kwargs)
    else:
        return url_for(*args, **kwargs)


def cache_key_prefix_view():
    scheme = 'https' if request.is_secure else 'http'
    return 'view/%s/%s' % (scheme, request.path)


LinkHeader = namedtuple(
    'LinkHeader', ['endpoint', 'values', 'params'])

PRECONNECT_HEADERS = [
    LinkHeader('index', {}, {'rel': 'preconnect'}),
    ]
JS_LINK_HEADERS = [
    LinkHeader('static', {'filename': 'js/main.js'}, {
            'rel': 'preload', 'as': 'script', 'nopush': True}),
    ]
CSS_LINK_HEADERS = [
    LinkHeader(
        'static', {'filename': 'css/main.css'}, {
            'rel': 'preload', 'as': 'style', 'nopush': True}),
    LinkHeader(
        'static', {'filename': 'fonts/RobotoCondensed-Light.woff'}, {
            'rel': 'preload', 'as': 'font', 'nopush': True,
            'crossorigin': True}),
    LinkHeader(
        'static', {'filename': 'fonts/RobotoCondensed-Regular.woff'}, {
            'rel': 'preload', 'as': 'font', 'nopush': True,
            'crossorigin': True}),
    LinkHeader(
        'static', {'filename': 'fonts/RobotoCondensed-Bold.woff'}, {
            'rel': 'preload', 'as': 'font', 'nopush': True,
            'crossorigin': True}),
    LinkHeader(
        'static', {'filename': 'fonts/MaterialIcons-Regular.woff2'}, {
            'rel': 'preload', 'as': 'font', 'nopush': True,
            'crossorigin': True}),
    LinkHeader(
        'fonts', {'name': 'Icons.woff2'}, {
            'rel': 'prefetch', 'as': 'font', 'nopush': True,
            'crossorigin': True}),
    ]


def add_links(links):
    def format_param(param):
        key, value = param
        if value is True:
            return key
        else:
            return '%s=%s' % (key, value)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            response = make_response(func(*args, **kwargs))
            for link in links:
                if (link.endpoint == 'index'
                        or (link.endpoint == 'static'
                            and link.values.get(
                                'filename', '').startswith('fonts/'))):
                    if (app.config['CDN_DOMAIN']
                            and not app.config['CDN_DEBUG']):
                        urls = app.url_map.bind(
                            app.config['CDN_DOMAIN'], url_scheme='https')
                        url = urls.build(
                            link.endpoint, link.values, force_external=True)
                    else:
                        url = url_for(link.endpoint, **link.values)
                else:
                    url = cdn_url_for(link.endpoint, **link.values)
                params = '; '.join(map(format_param, link.params.items()))
                value = '<{url}>; {params}'.format(
                    url=url,
                    params=params)
                response.headers.add('Link', value)
            return response
        return wrapper
    return decorator


@app.after_request
def add_cache_control_header(response):
    if 'Cache-Control' not in response.headers:
        response.cache_control.max_age = app.config['CACHE_DEFAULT_TIMEOUT']
        response.cache_control.public = True
    return response


def url_for_canonical(endpoint=None, **values):
    if endpoint is None:
        endpoint = request.endpoint
    if not endpoint:
        return ''
    scheme = 'https' if not app.debug else None
    return url_for(endpoint, _external=True, _scheme=scheme, **values)


@app.context_processor
def inject_canonical():
    return dict(url_for_canonical=url_for_canonical)


@cache.memoize(timeout=365 * 24 * 60 * 60)
def dominant_color(path):
    if app.debug:
        return '#000'
    color = ColorThief(
        os.path.join(app.static_folder, path)).get_color(quality=1)
    return '#%02x%02x%02x' % color


@app.context_processor
def inject_dominant_color():
    return dict(dominant_color=dominant_color)


HEART = ('<span '
    'class="material-icons beat" aria-hidden="true" '
    'style="color:#d9534f; font-size: inherit; vertical-align: middle">'
    'favorite'
    '</span>')


@app.route('/')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def index():
    return render_template(
        'index.html',
        news=list(news_items(3)),
        next_events=next_events(3))


@app.context_processor
def inject_menu():
    menu = OrderedDict()
    menu['Tryton'] = [
        ('Success Stories', url_for('success_stories')),
        ('News', url_for('news')),
        ('Get Tryton', url_for('download')),
        ('Documentation', '//docs.tryton.org/'),
        ]
    menu['Community'] = [
        ('Forum', url_for('forum')),
        ('Presentations', url_for('presentations')),
        ('Get Help', 'https://discuss.tryton.org/c/support'),
        ('Contribute', url_for('contribute')),
        ]
    menu['Foundation'] = [
        ('About', url_for('foundation')),
        ('Supporters', url_for('supporters')),
        (HEART + ' Donations', url_for('donate')),
        ]
    menu['Services'] = [
        ('Service Providers', url_for('service_providers')),
        ('Become a Service Provider', url_for('service_providers_start')),
        ]
    return dict(menu=menu, datetime=datetime)


@app.context_processor
def inject_copyright_dates():
    return dict(copyright_dates='2008-%s' % datetime.date.today().year)


@app.context_processor
def inject_heart():
    return dict(heart=HEART)


@app.route('/robots.txt')
@cache.cached()
def static_from_root():
    response = make_response(render_template('robots.txt'))
    response.mimetype = 'text/plain'
    return response


@app.route('/news')
@app.route('/news/index.html', endpoint='news-alt')
def news():
    return redirect(NEWS_URL)


@app.route('/news.rss')
@app.route('/rss.xml')
def news_rss():
    return redirect(NEWS_RSS_URL)


@cache.memoize(timeout=60 * 60)
def fetch_news_items():
    return requests.get(NEWS_RSS_URL).content


def news_items(size=-1):
    try:
        root = objectify.fromstring(fetch_news_items())
    except Exception:
        app.logger.error('fail to fetch news', exc_info=True)
        return
    for item in root.xpath('/rss/channel/item')[:size]:
        yield item


@app.template_filter('news_text')
def news_text(content):
    block = html.fromstring(str(content))
    for box in block.find_class('lightbox-wrapper'):
        box.drop_tree()
    return block.text_content().strip()


@app.route('/events')
@app.route('/events.html', endpoint='events-alt')
def events():
    return redirect(CALENDAR_URL)


@cache.memoize(timeout=60 * 60 * 24)
def fetch_events():
    ics = requests.get(CALENDAR_ICS)
    return ics.content


def next_events(size=-1):
    today = datetime.date.today()
    try:
        cal = Calendar.from_ical(fetch_events())
    except Exception:
        app.logger.error('fail to fetch events', exc_info=True)
        return []

    events = []
    for event in cal.walk('vevent'):
        end_date = (event.get('dtend') or event.get('dtstart')).dt
        if date(end_date) >= today:
            events.append(event)

    def start_date(event):
        return date(event.get('dtstart').dt)

    return sorted(events, key=start_date)[:size]


@app.template_filter('date')
def date(datetime):
    if hasattr(datetime, 'date'):
        return datetime.date()
    return datetime


class Case:
    def __init__(self, title, description, story=False):
        self.title = title
        self.description = description
        self.story = story

    @property
    def name(self):
        return slugify(self.title.lower())

    @property
    def url(self):
        if self.story:
            return url_for('success_story', story=self.name)

    @property
    def logo(self):
        return 'images/success-stories/%s.jpg' % self.name

    def __eq__(self, other):
        if isinstance(other, str):
            return self.name == other
        elif isinstance(other, Case):
            return self.name == other.name
        return NotImplemented


CASES = [
    Case(title="ALS Swiss",
        description="A society for people suffering ALS disease.",
        story=True),
    Case(
        title="AMMEBA",
        description="A Medical Mutual Society from Buenos Aires.",
        story=True),
    Case(
        title="Advocate Consulting Legal Group",
        description="A legal firm servicing the general aviation industry",
        story=True),
    Case(
        title="Banque Française Mutualiste",
        description="A French bank for the public service."),
    Case(
        title="Blue Box Distribution",
        description="An international distributor of hair care products.",
        story=True),
    Case(
        title="CAMIR",
        description="A provider of spare parts for machinery.",
        story=True),
    Case(
        title="La Cave Thrace",
        description="Imports and distributes wine in France."),
    Case(
        title="Cultural Commons Collection Society",
        description="Collects and distributes music royalties."),
    Case(
        title="Expertise Vision",
        description="Produces vision based systems.",
        story=True),
    Case(
        title="Felber",
        description="A stamp and signalisation company.",
        story=True),
    Case(
        title="GotSHO LIMS",
        description="Software Solution for genomic world.",
        story=True),
    Case(
        title="Grufesa",
        description="Exports strawberries in Europe.",
        story=True),
    Case(
        title="Institut Mèdic per la Imatge",
        description="Provides all kinds of MRI scans, nuclear medicine "
        "and bone densitometry."),
    Case(
        title="Jordà",
        description="Installs and maintains lifts and elevators.",
        story=True),
    Case(
        title="Legna",
        description="Graphic design, digital printing "
        "and offset solution company",
        story=True),
    Case(
        title="Koolvet",
        description="Software for veterinary clinics that deal with small "
        "domestic pets and larger farm animals.",
        story=True),
    Case(
        title="MenschensKinder Teltow",
        description="Operates municipal day care centers and "
        "parent-child groups."),
    Case(
        title="Lackierzentrum Reichenbach",
        description="Produces surface coating for automotive, aerospace, "
        "construction and mechanical engineering."),
    Case(
        title="Revelle",
        description="Consulting in developing countries and "
        "emerging economies.",
        story=True),
    Case(
        title="Sinclair Containers",
        description="Sells and rents containers."),
    Case(
        title="Skoda Autohaus Zeidler",
        description="A German car dealership and workshop for Skoda."),
    ]


@app.route('/success-stories')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def success_stories():
    cases = sorted(
        sample(CASES, len(CASES)), key=attrgetter('story'), reverse=True)
    return render_template('success_stories.html', cases=cases)


@app.route('/business-cases.html', endpoint='success_stories-alt')
def success_stories_alt():
    return redirect(url_for('success_stories'))


@app.route('/success-stories/<story>')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def success_story(story):
    cases = [c for c in CASES if c.story or c.name == story]
    try:
        next_case = cases[(cases.index(story) + 1) % len(cases)]
    except ValueError:
        abort(HTTPStatus.NOT_FOUND)
    try:
        return render_template(
            'success_stories/%s.html' % story, next_case=next_case,
            canonical=url_for_canonical(story=story))
    except TemplateNotFound:
        abort(HTTPStatus.NOT_FOUND)


@sitemap.register_generator
def success_story_generator():
    for case in CASES:
        if case.url:
            yield 'success_story', dict(story=case.name)


@app.route('/download')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def download():
    return render_template('download.html')


@app.route('/download.html', endpoint='download-alt')
def download_alt():
    return redirect(url_for('download'))


@app.route('/forum')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def forum():
    return render_template('forum.html')


@app.route('/presentations')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def presentations():
    return render_template('presentations.html')


@app.route('/papers.html', endpoint='presentations-alt')
def presentations_alt():
    return redirect(url_for('presentations'))


@app.route('/events/<event>')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def event(event):
    class Day:
        def __init__(self, date, *events, location=None, full=False):
            if not isinstance(date, datetime.date):
                date = datetime.date(*date)
            self.date = date
            self.full = full
            self.location = location
            self.events = []
            for event in events:
                self.add(*event)

        def add(self, summary, start, end, *args, location=None):
            if not isinstance(start, datetime.time):
                start = datetime.time(*start)
            if not isinstance(end, datetime.time):
                end = datetime.time(*end)
            start = datetime.datetime.combine(self.date, start)
            end = datetime.datetime.combine(self.date, end)
            if not location:
                location = self.location
            self.events.append(Event(
                    summary, start, end, *args, location=location))

        @property
        def start(self):
            if self.events:
                return min(e.start for e in self.events)

        @property
        def end(self):
            if self.events:
                return max(e.end for e in self.events)

    class Event:
        def __init__(self, summary, start, end, description='', profiles=(),
                location=None):
            self.summary = summary
            self.start = start
            self.end = end
            self.location = location
            self.description = description
            self.profiles = [Profile(*p) for p in profiles]

    class Profile:
        def __init__(self, name, gravatar, company='', url=''):
            self.name = name
            self.gravatar = gravatar
            self.company = company
            self.url = url
    try:
        return render_template(
            'events/%s.html' % event, Day=Day,
            canonical=url_for_canonical(event=event))
    except TemplateNotFound:
        abort(HTTPStatus.NOT_FOUND)


@app.route('/contribute')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def contribute():
    return render_template('contribute.html')


@app.route('/how-to-contribute.html', endpoint='contribute-alt')
def contribute_alt():
    return redirect(url_for('contribute'))


@app.route('/develop')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def develop():
    return render_template('develop.html')


@app.route('/develop/guidelines/code')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def guidelines_code():
    return render_template('guidelines/code.html')


@app.route('/develop/guidelines/documentation')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def guidelines_documentation():
    return render_template('guidelines/documentation.html')


@app.route('/develop/guidelines/help-text')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def guidelines_documentation_help():
    return render_template('guidelines/help.html')


@app.route('/develop/guidelines/howto')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def guidelines_documentation_howto():
    return render_template('guidelines/howto.html')


@app.route('/foundation')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def foundation():
    return render_template('foundation.html')


@app.route('/foundation/', endpoint='foundation-alt')
def foundation_alt():
    return redirect(url_for('foundation'))


@cache.memoize(timeout=60 * 60 * 24)
def fetch_supporters():
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.get(SUPPORTERS_URL, headers=headers)
        return response.json()
    except Exception:
        app.logger.error('fail to fetch supporters', exc_info=True)
        return []


@app.route('/supporters')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def supporters():
    def url(supporter, start):
        for website in supporter['websites']:
            if website.startswith(start):
                return website
    return render_template('supporters.html',
        supporters=fetch_supporters(),
        discuss_url=partial(url, start='https://discuss.tryton.org/'),
        roundup_url=partial(url, start='https://bugs.tryton.org/'))


@app.route('/foundation/supporters.html', endpoint='supporters-alt')
def supporters_alt():
    return redirect(url_for('supporters'))


@cache.memoize(timeout=60 * 60 * 24)
def fetch_gravatar(hash, **params):
    url = 'https://secure.gravatar.com/avatar/' + hash
    response = requests.get(url, params=params)
    response.raise_for_status()
    rv = make_response(response.content)
    rv.content_type = response.headers['Content-Type']
    rv.cache_control.max_age = 60 * 60 * 24
    rv.cache_control.public = True
    return rv


@app.route('/avatar/<hash>')
@cache.cached(query_string=True)
def avatar(hash):
    if not set(request.args.keys()).issubset(set('sdr')):
        abort(HTTPStatus.BAD_REQUEST)
    return fetch_gravatar(hash, **request.args)


@app.template_filter('hostname')
def hostname(url):
    return urlparse(url).hostname


@cache.memoize(timeout=60 * 60 * 24)
def fetch_donators():
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.get(DONATORS_URL, headers=headers)
        return response.json()
    except Exception:
        app.logger.error('fail to fetch donators', exc_info=True)
        return []


@cache.memoize(timeout=60 * 60 * 24)
def fetch_donations():
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.get(DONATIONS_URL, headers=headers)
        return response.json()
    except Exception:
        app.logger.error('fail to fetch donations', exc_info=True)
        return []


@app.route('/donate')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def donate():
    return render_template('donate.html',
        donators=fetch_donators(),
        donations=fetch_donations())


@app.route('/foundation/donations.html', endpoint='donate-alt')
def donate_alt():
    return redirect(url_for('donate'))


@app.route('/donate/thanks')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def donate_thanks():
    return render_template('donate_thanks.html')


@app.route('/donate/cancel')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def donate_cancel():
    return render_template('donate_cancel.html')


@app.route('/service-providers')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def service_providers():
    shuffle(PROVIDERS)
    return render_template('service_providers.html', providers=PROVIDERS)


@app.route('/services.html', endpoint='service_providers-alt')
def service_providers_alt():
    return redirect(url_for('service_providers'))


@app.route('/service-providers/start')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def service_providers_start():
    return render_template('service_providers_start.html')


@app.route('/fonts/<name>')
def fonts(name):
    return redirect(cdn_url_for('static', filename='fonts/' + name))


@app.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='images/favicon.ico'))


@app.route('/_warmup')
def warmup():
    fetch_news_items()
    fetch_events()
    for supporter in fetch_supporters():
        hash = hashlib.md5(supporter['email'].encode('utf-8')).hexdigest()
        try:
            fetch_gravatar(
                hash, s='198', d=gravatar.default, r=gravatar.rating)
        except Exception:
            app.logger.warning('fail to fetch gravatar')
    for path in glob.glob(os.path.join(app.static_folder, '**/*.jpg')):
        dominant_color(os.path.relpath(path, app.static_folder))
    return '', HTTPStatus.NO_CONTENT


@app.errorhandler(HTTPStatus.NOT_FOUND)
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def not_found(error):
    return render_template(
        'not_found.html', canonical=None), HTTPStatus.NOT_FOUND


class RequestFormatter(logging.Formatter):
    def format(self, record):
        record.url = request.url
        record.remote_addr = request.remote_addr
        return super().format(record)


mail_handler = SMTPHandler(
    mailhost='mx.tryton.org',
    fromaddr='www@tryton.org',
    toaddrs=['webmaster@tryton.org'],
    subject="[www.tryton.org] Application Error",
    )
mail_handler.setLevel(logging.ERROR)
formatter = RequestFormatter(
    '[%(asctime)s] %(remote_addr)s requested %(url)s\n'
    '%(levelname)s in %(module)s: %(message)s'
    )
default_handler.setFormatter(formatter)
mail_handler.setFormatter(formatter)

if __name__ == '__main__':
    app.config['CDN_DEBUG'] = ast.literal_eval(
        os.environ.get('CDN_DEBUG', 'True'))
    app.run(
        debug=ast.literal_eval(os.environ.get('DEBUG', 'True')),
        extra_files=[
            'templates',
            'templates/service_providers',
            'templates/events',
            'templates/success_stories',
            ])

if not app.debug:
    app.logger.addHandler(mail_handler)
